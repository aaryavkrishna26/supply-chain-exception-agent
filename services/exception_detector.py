"""
Deterministic Exception Detection Engine for Supply Chain Operations.

Performs rule-based detection for:
1. Logistics: Shipment delays & Carrier breakdowns
2. Procurement: Purchase order delays & Supplier capacity constraints
3. Inventory: Warehouse stockout risks & reorder thresholds
4. Cross-Functional: Customer SLA breaches caused by upstream shipment or inventory bottlenecks
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from database.client import get_db
from database.queries.exceptions import ExceptionQueries
from services.audit_service import AuditService
from services.ml_prediction_service import MLPredictionService

logger = logging.getLogger("exception_detector")


class ExceptionDetector:

    def __init__(self):
        self.db = get_db()

    def run_all_detectors(self) -> List[Dict[str, Any]]:
        """Run all deterministic exception detection rules and persist newly found exceptions."""
        detected = []
        logger.info("Starting deterministic exception detection scan...")

        detected.extend(self.detect_shipment_delays())
        detected.extend(self.detect_purchase_order_delays())
        detected.extend(self.detect_inventory_shortages())
        detected.extend(self.detect_supplier_capacity_issues())

        logger.info(f"Scan complete. Total new exceptions detected & persisted: {len(detected)}")
        return detected

    def detect_shipment_delays(self) -> List[Dict[str, Any]]:
        """
        Detect shipments that:
        1. Are explicitly marked as DELAYED or EXCEPTION.
        2. Have passed expected_delivery_date without DELIVERED status.
        3. Have actual_delivery_date > expected_delivery_date.

        ML Enhancement: Each active shipment is also scored by the
        MLPredictionService. Shipments with a predicted delay probability
        > 0.70 that have not yet crossed the deadline receive a proactive
        PREDICTED_DELIVERY_DELAY exception so the agent can act early.
        """
        new_exceptions = []

        # --- Rule-based: already delayed / past deadline ---
        sql_delayed = """
            SELECT s.*, c.name as carrier_name, o.order_number, o.priority as order_priority, o.customer_id,
                   o.total_amount AS order_value, po.total_cost AS po_value
            FROM shipments s
            JOIN carriers c ON s.carrier_id = c.id
            LEFT JOIN orders o ON s.order_id = o.id
            LEFT JOIN purchase_orders po ON s.purchase_order_id = po.id
            WHERE s.status IN ('DELAYED', 'EXCEPTION')
               OR (s.status NOT IN ('DELIVERED', 'CANCELLED') AND s.expected_delivery_date < CURRENT_TIMESTAMP)
        """
        rows = self.db.execute_query(sql_delayed)

        for row in rows:
            # Check if active exception already exists for this shipment
            existing = self.db.execute_query(
                "SELECT id FROM exceptions WHERE shipment_id = :sid AND status IN ('OPEN', 'INVESTIGATING', 'PENDING_APPROVAL')",
                {"sid": row["id"]}
            )
            if existing:
                continue

            # --- ML Risk Score ---
            ml_result = MLPredictionService.predict_delay_risk(row)
            ml_prob   = ml_result["probability"]
            ml_label  = ml_result["risk_label"]
            ml_source = ml_result["model"]
            ml_note   = (
                f" | ML Delay Risk: {ml_label} ({ml_prob:.0%}, model={ml_source})"
            )

            exc_id = f"EXC-LOG-{uuid.uuid4().hex[:6].upper()}"
            is_critical_order = row.get("order_priority") in ("HIGH", "CRITICAL")
            severity = "CRITICAL" if is_critical_order else ("HIGH" if row.get("delay_hours", 0) > 12 else "MEDIUM")

            category = "CROSS_FUNCTIONAL" if (row.get("order_id") and is_critical_order) else "LOGISTICS"
            title = f"Shipment Delay: {row['shipment_number']} ({row.get('carrier_name', 'Carrier')})"
            desc = (
                f"Shipment {row['shipment_number']} from {row['origin_location']} to {row['destination_location']} "
                f"is delayed by approx {row.get('delay_hours', 0)} hours. Current location: {row.get('current_location') or 'not reported'}. "
                f"Notes: {row.get('tracking_notes') or 'none recorded'}.{ml_note}"
            )

            record = {
                "id": exc_id,
                "exception_code": f"EXP-SHP-{row['shipment_number']}",
                "category": category,
                "exception_type": "SHIPMENT_DELAY",
                "severity": severity,
                "status": "OPEN",
                "order_id": row.get("order_id"),
                "shipment_id": row["id"],
                "purchase_order_id": row.get("purchase_order_id"),
                "warehouse_id": None,
                "product_id": None,
                "title": title,
                "description": desc,
                # Exposure: 20% of the goods on board (the procurement rule), because SCMS
                # often records freight as included in commodity cost; freight x 1.5 otherwise.
                "estimated_financial_loss": (
                    float(row.get("order_value") or row.get("po_value") or 0.0) * 0.20
                    or float(row.get("shipping_cost") or 0.0) * 1.5
                ),
            }

            ExceptionQueries.create_exception(record)
            AuditService.log_step(
                exception_id=exc_id,
                agent_step="DETECTION",
                tool_called="detect_shipment_delays",
                input_payload={"shipment_id": row["id"], "ml_risk": ml_result},
                output_payload=record,
                decision=f"Flagged {severity} logistics exception for shipment {row['shipment_number']} (ML risk={ml_label} {ml_prob:.0%})"
            )
            new_exceptions.append(record)

        # --- ML Proactive: high-risk shipments not yet overdue ---
        new_exceptions.extend(self._detect_predicted_delays())

        return new_exceptions

    def _detect_predicted_delays(self) -> List[Dict[str, Any]]:
        """
        Query active shipments that are still within their delivery window
        and flag any whose ML-predicted delay probability exceeds 70%.
        These become PREDICTED_DELIVERY_DELAY exceptions so the agent can
        act before the deadline is missed.
        """
        new_exceptions = []
        sql = """
            SELECT s.*, c.name as carrier_name, o.order_number, o.priority as order_priority, o.customer_id,
                   o.total_amount AS order_value, po.total_cost AS po_value
            FROM shipments s
            JOIN carriers c ON s.carrier_id = c.id
            LEFT JOIN orders o ON s.order_id = o.id
            LEFT JOIN purchase_orders po ON s.purchase_order_id = po.id
            WHERE s.status IN ('CREATED', 'IN_TRANSIT', 'OUT_FOR_DELIVERY')
              AND (s.expected_delivery_date IS NULL OR s.expected_delivery_date >= CURRENT_TIMESTAMP)
            LIMIT 200
        """
        rows = self.db.execute_query(sql)
        for row in rows:
            ml_result = MLPredictionService.predict_delay_risk(row)
            if ml_result["probability"] < 0.70:
                continue

            # Skip if a predicted-delay exception already exists
            existing = self.db.execute_query(
                "SELECT id FROM exceptions WHERE shipment_id = :sid "
                "AND exception_type = 'PREDICTED_DELIVERY_DELAY' "
                "AND status IN ('OPEN', 'INVESTIGATING', 'PENDING_APPROVAL')",
                {"sid": row["id"]}
            )
            if existing:
                continue

            ml_prob  = ml_result["probability"]
            ml_label = ml_result["risk_label"]
            ml_source = ml_result["model"]

            exc_id = f"EXC-PML-{uuid.uuid4().hex[:6].upper()}"
            title = (
                f"Predicted Delay Risk: {row['shipment_number']} "
                f"({row.get('carrier_name', 'Carrier')}) — {ml_label} ({ml_prob:.0%})"
            )
            desc = (
                f"ML model ({ml_source}) predicts a {ml_prob:.0%} probability of delay for "
                f"shipment {row['shipment_number']} travelling from {row['origin_location']} "
                f"to {row['destination_location']}. The shipment is still within its delivery "
                f"window — proactive action is recommended to prevent an SLA breach."
            )

            record = {
                "id": exc_id,
                "exception_code": f"EXP-PML-{row['shipment_number']}",
                "category": "LOGISTICS",
                "exception_type": "PREDICTED_DELIVERY_DELAY",
                "severity": "HIGH" if ml_prob >= 0.85 else "MEDIUM",
                "status": "OPEN",
                "order_id": row.get("order_id"),
                "shipment_id": row["id"],
                "purchase_order_id": row.get("purchase_order_id"),
                "warehouse_id": None,
                "product_id": None,
                "title": title,
                "description": desc,
                "estimated_financial_loss": (
                    float(row.get("order_value") or row.get("po_value") or 0.0) * 0.10
                    or float(row.get("shipping_cost") or 0.0) * 1.0
                ),
            }

            ExceptionQueries.create_exception(record)
            AuditService.log_step(
                exception_id=exc_id,
                agent_step="DETECTION",
                tool_called="ml_predict_delay",
                input_payload={"shipment_id": row["id"], "ml_result": ml_result},
                output_payload=record,
                decision=f"Proactive ML flag: {row['shipment_number']} has {ml_prob:.0%} delay probability"
            )
            new_exceptions.append(record)
            logger.info(
                "[ML] Proactive exception created for shipment %s (prob=%.2f, model=%s)",
                row["shipment_number"], ml_prob, ml_source,
            )

        return new_exceptions

    def detect_purchase_order_delays(self) -> List[Dict[str, Any]]:
        """
        Detect purchase orders where:
        1. Status is DELAYED.
        2. Expected delivery date has passed and status is not RECEIVED / CANCELLED.
        """
        new_exceptions = []
        sql = """
            SELECT po.*, s.name as supplier_name, s.reliability_rating, s.code as supplier_code,
                   w.name as destination_warehouse_name
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.id
            JOIN warehouses w ON po.destination_warehouse_id = w.id
            WHERE po.status IN ('DELAYED')
               OR (po.status NOT IN ('RECEIVED', 'CANCELLED') AND po.expected_delivery_date < CURRENT_TIMESTAMP)
        """
        rows = self.db.execute_query(sql)

        for row in rows:
            existing = self.db.execute_query(
                "SELECT id FROM exceptions WHERE purchase_order_id = :poid AND status IN ('OPEN', 'INVESTIGATING', 'PENDING_APPROVAL')",
                {"poid": row["id"]}
            )
            if existing:
                continue

            exc_id = f"EXC-PRC-{uuid.uuid4().hex[:6].upper()}"
            title = f"PO Delay: {row['po_number']} from {row['supplier_name']}"
            desc = (
                f"Purchase Order {row['po_number']} for warehouse '{row['destination_warehouse_name']}' is overdue. "
                f"Supplier reliability is {float(row.get('reliability_rating', 1.0)):.0%}. Notes: {row.get('notes', 'None')}."
            )

            record = {
                "id": exc_id,
                "exception_code": f"EXP-PO-{row['po_number']}",
                "category": "PROCUREMENT",
                "exception_type": "PURCHASE_ORDER_DELAY",
                "severity": "HIGH",
                "status": "OPEN",
                "order_id": None,
                "shipment_id": None,
                "purchase_order_id": row["id"],
                "warehouse_id": row["destination_warehouse_id"],
                "product_id": None,
                "title": title,
                "description": desc,
                "estimated_financial_loss": float(row.get("total_cost", 0.0)) * 0.20,
            }

            ExceptionQueries.create_exception(record)
            AuditService.log_step(
                exception_id=exc_id,
                agent_step="DETECTION",
                tool_called="detect_purchase_order_delays",
                input_payload={"purchase_order_id": row["id"]},
                output_payload=record,
                decision=f"Flagged procurement exception for PO {row['po_number']}"
            )
            new_exceptions.append(record)

        return new_exceptions

    def detect_inventory_shortages(self) -> List[Dict[str, Any]]:
        """
        Detect inventory records where available stock is below safety stock or reorder point.
        """
        new_exceptions = []
        sql = """
            SELECT i.*, w.name as warehouse_name, p.name as product_name, p.sku, p.critical_level, p.unit_price
            FROM inventory i
            JOIN warehouses w ON i.warehouse_id = w.id
            JOIN products p ON i.product_id = p.id
            WHERE i.quantity_available <= i.safety_stock
        """
        rows = self.db.execute_query(sql)

        for row in rows:
            existing = self.db.execute_query(
                "SELECT id FROM exceptions WHERE warehouse_id = :wid AND product_id = :pid AND status IN ('OPEN', 'INVESTIGATING', 'PENDING_APPROVAL')",
                {"wid": row["warehouse_id"], "pid": row["product_id"]}
            )
            if existing:
                continue

            exc_id = f"EXC-INV-{uuid.uuid4().hex[:6].upper()}"
            is_critical = row["critical_level"] in ("CRITICAL", "HIGH")
            severity = "CRITICAL" if (row["quantity_available"] == 0 or is_critical) else "MEDIUM"

            title = f"Inventory Shortage: {row['product_name']} at {row['warehouse_name']}"
            desc = (
                f"Available inventory for {row['sku']} ({row['product_name']}) at {row['warehouse_name']} "
                f"is {row['quantity_available']} units, below safety stock threshold of {row['safety_stock']} units."
            )

            record = {
                "id": exc_id,
                "exception_code": f"EXP-INV-{row['warehouse_id']}-{row['product_id']}",
                "category": "INVENTORY",
                "exception_type": "INVENTORY_SHORTAGE",
                "severity": severity,
                "status": "OPEN",
                "order_id": None,
                "shipment_id": None,
                "purchase_order_id": None,
                "warehouse_id": row["warehouse_id"],
                "product_id": row["product_id"],
                "title": title,
                "description": desc,
                "estimated_financial_loss": float(row["unit_price"]) * float(row["reorder_point"] - row["quantity_available"]),
            }

            ExceptionQueries.create_exception(record)
            AuditService.log_step(
                exception_id=exc_id,
                agent_step="DETECTION",
                tool_called="detect_inventory_shortages",
                input_payload={"warehouse_id": row["warehouse_id"], "product_id": row["product_id"]},
                output_payload=record,
                decision=f"Flagged inventory shortage exception for product {row['sku']} at warehouse {row['warehouse_name']}"
            )
            new_exceptions.append(record)

        return new_exceptions

    def detect_supplier_capacity_issues(self) -> List[Dict[str, Any]]:
        """
        Detect suppliers whose current capacity utilization is >= 95% of daily maximum.
        """
        new_exceptions = []
        sql = """
            SELECT * FROM suppliers
            WHERE (current_capacity_utilized * 1.0 / NULLIF(capacity_units_per_day, 0)) >= 0.95
              AND is_active = TRUE
        """
        rows = self.db.execute_query(sql)

        for row in rows:
            existing = self.db.execute_query(
                "SELECT id FROM exceptions WHERE title LIKE :title AND status IN ('OPEN', 'INVESTIGATING', 'PENDING_APPROVAL')",
                {"title": f"%Supplier Capacity Constraint: {row['name']}%"}
            )
            if existing:
                continue

            exc_id = f"EXC-SUP-{uuid.uuid4().hex[:6].upper()}"
            title = f"Supplier Capacity Constraint: {row['name']}"
            utilization_pct = (row["current_capacity_utilized"] / row["capacity_units_per_day"]) * 100
            desc = (
                f"Supplier {row['name']} ({row['code']}) is operating at {utilization_pct:.1f}% capacity "
                f"({row['current_capacity_utilized']}/{row['capacity_units_per_day']} units/day), creating procurement lead-time bottleneck."
            )

            record = {
                "id": exc_id,
                "exception_code": f"EXP-CAP-{row['code']}",
                "category": "PROCUREMENT",
                "exception_type": "SUPPLIER_CAPACITY_BOTTLENECK",
                "severity": "MEDIUM",
                "status": "OPEN",
                "order_id": None,
                "shipment_id": None,
                "purchase_order_id": None,
                "warehouse_id": None,
                "product_id": None,
                "title": title,
                "description": desc,
                "estimated_financial_loss": 50000.0,
            }

            ExceptionQueries.create_exception(record)
            AuditService.log_step(
                exception_id=exc_id,
                agent_step="DETECTION",
                tool_called="detect_supplier_capacity_issues",
                input_payload={"supplier_id": row["id"]},
                output_payload=record,
                decision=f"Flagged supplier capacity bottleneck for {row['name']}"
            )
            new_exceptions.append(record)

        return new_exceptions


def run_detection():
    detector = ExceptionDetector()
    return detector.run_all_detectors()


if __name__ == "__main__":
    exceptions = run_detection()
    print(f"\n--- Detection Run Finished: Found {len(exceptions)} Exceptions ---")
    for e in exceptions:
        print(f"[{e['severity']}] [{e['category']}] {e['title']}")
