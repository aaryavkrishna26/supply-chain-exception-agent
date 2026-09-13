"""
Execution Tools for Supply Chain Exception Resolution.
Executes approved operational actions directly against live Supabase PostgreSQL.
Provides state verification, idempotency protection, and audit logging.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from database.queries.supply_chain import SupplyChainQueries
from database.queries.exceptions import ExceptionQueries
from models.schemas import ExecutionStatus, ExecutionResult

logger = logging.getLogger("resolution_tools")


def _log_audit_step(*args, **kwargs):
    from services.audit_service import AuditService
    return AuditService.log_step(*args, **kwargs)




def execute_inventory_transfer(
    exception_id: str,
    from_warehouse_id: Optional[str] = None,
    to_warehouse_id: Optional[str] = None,
    product_id: Optional[str] = None,
    quantity: Optional[int] = None,
    resolution_option_id: Optional[str] = None,
    notes: Optional[str] = None,
    executed_by: str = "SYSTEM_AGENT",
    source_warehouse_id: Optional[str] = None,
    destination_warehouse_id: Optional[str] = None,
) -> ExecutionResult:
    """
    Execute an inventory transfer between warehouses in Supabase PostgreSQL.
    Verifies source stock, shifts quantities, creates action record, updates exception to RESOLVED,
    and logs the audit trail.
    """
    src_wh = source_warehouse_id or from_warehouse_id
    dest_wh = destination_warehouse_id or to_warehouse_id

    if not src_wh or not dest_wh or not product_id or not quantity or quantity <= 0:
        raise ValueError(
            f"Invalid execution parameters for inventory transfer: "
            f"product_id={product_id}, source_warehouse_id={src_wh}, "
            f"destination_warehouse_id={dest_wh}, quantity={quantity}"
        )

    logger.info(
        f"Executing inventory transfer: {quantity} units of {product_id} "
        f"from {src_wh} to {dest_wh} for exception {exception_id}"
    )

    # 1. Idempotency check
    if resolution_option_id and ExceptionQueries.has_action_for_option(resolution_option_id):
        raise RuntimeError(f"Action for resolution option {resolution_option_id} has already been executed.")

    # 2. Execute DB inventory update
    transfer_diff = SupplyChainQueries.transfer_inventory(
        from_warehouse_id=src_wh,
        to_warehouse_id=dest_wh,
        source_warehouse_id=src_wh,
        destination_warehouse_id=dest_wh,
        product_id=product_id,
        quantity=quantity
    )

    action_id = f"ACT-XFR-{uuid.uuid4().hex[:6].upper()}"
    result_message = (
        f"Successfully transferred {quantity} units of product {product_id} "
        f"from warehouse {src_wh} to {dest_wh}. "
        f"Source available: {transfer_diff['source_available_before']} -> {transfer_diff['source_available_after']}. "
        f"Dest available: {transfer_diff['dest_available_before']} -> {transfer_diff['dest_available_after']}."
    )

    payload = {
        "source_warehouse_id": src_wh,
        "destination_warehouse_id": dest_wh,
        "from_warehouse_id": src_wh,
        "to_warehouse_id": dest_wh,
        "product_id": product_id,
        "quantity": quantity,
        "notes": notes,
        "state_diff": transfer_diff
    }

    # 3. Create action record
    ExceptionQueries.record_action({
        "id": action_id,
        "exception_id": exception_id,
        "resolution_option_id": resolution_option_id,
        "action_type": "INVENTORY_TRANSFER",
        "executed_by": executed_by,
        "execution_status": "SUCCESS",
        "payload": payload,
        "result_message": result_message
    })

    # 4. Update exception status to RESOLVED
    ExceptionQueries.update_exception_status(
        exception_id=exception_id,
        status="RESOLVED"
    )

    # 5. Create audit log
    _log_audit_step(
        exception_id=exception_id,
        agent_step="ACTION_EXECUTED",
        tool_called="execute_inventory_transfer",
        input_payload={
            "source_warehouse_id": src_wh,
            "destination_warehouse_id": dest_wh,
            "from_warehouse_id": src_wh,
            "to_warehouse_id": dest_wh,
            "product_id": product_id,
            "quantity": quantity
        },
        output_payload=transfer_diff,
        decision=result_message
    )

    return ExecutionResult(
        action_id=action_id,
        exception_id=exception_id,
        resolution_option_id=resolution_option_id,
        action_type="INVENTORY_TRANSFER",
        status=ExecutionStatus.SUCCESS,
        result_message=result_message,
        verified_db_changes=transfer_diff,
        executed_at=datetime.now(timezone.utc)
    )


def execute_shipment_reroute(
    exception_id: str,
    shipment_id: str,
    new_route_id: str,
    resolution_option_id: Optional[str] = None,
    notes: Optional[str] = None,
    executed_by: str = "SYSTEM_AGENT",
) -> ExecutionResult:
    """
    Execute a shipment reroute in Supabase PostgreSQL.
    Updates shipment route_id, marks status as 'REROUTED', appends notes,
    creates action record, updates exception to RESOLVED, and logs the audit trail.
    """
    logger.info(f"Executing shipment reroute: shipment {shipment_id} to route {new_route_id}")

    # 1. Idempotency check
    if resolution_option_id and ExceptionQueries.has_action_for_option(resolution_option_id):
        raise RuntimeError(f"Action for resolution option {resolution_option_id} has already been executed.")

    # 2. Execute DB shipment update
    diff = SupplyChainQueries.update_shipment_routing_carrier(
        shipment_id=shipment_id,
        route_id=new_route_id,
        status="REROUTED",
        tracking_notes=f"Rerouted to alternative route {new_route_id}. Reason: {notes or 'Bypassing disruption'}"
    )

    action_id = f"ACT-RRT-{uuid.uuid4().hex[:6].upper()}"
    result_message = (
        f"Successfully rerouted shipment {shipment_id} to route {new_route_id}. "
        f"Route: {diff['before']['route_id']} -> {diff['after']['route_id']}. "
        f"Status: {diff['before']['status']} -> {diff['after']['status']}."
    )

    payload = {
        "shipment_id": shipment_id,
        "new_route_id": new_route_id,
        "notes": notes,
        "state_diff": diff
    }

    # 3. Create action record
    ExceptionQueries.record_action({
        "id": action_id,
        "exception_id": exception_id,
        "resolution_option_id": resolution_option_id,
        "action_type": "SHIPMENT_REROUTE",
        "executed_by": executed_by,
        "execution_status": "SUCCESS",
        "payload": payload,
        "result_message": result_message
    })

    # 4. Update exception status to RESOLVED
    ExceptionQueries.update_exception_status(
        exception_id=exception_id,
        status="RESOLVED"
    )

    # 5. Create audit log
    _log_audit_step(
        exception_id=exception_id,
        agent_step="ACTION_EXECUTED",
        tool_called="execute_shipment_reroute",
        input_payload={"shipment_id": shipment_id, "new_route_id": new_route_id},
        output_payload=diff,
        decision=result_message
    )

    return ExecutionResult(
        action_id=action_id,
        exception_id=exception_id,
        resolution_option_id=resolution_option_id,
        action_type="SHIPMENT_REROUTE",
        status=ExecutionStatus.SUCCESS,
        result_message=result_message,
        verified_db_changes=diff,
        executed_at=datetime.now(timezone.utc)
    )


def execute_carrier_change(
    exception_id: str,
    shipment_id: str,
    new_carrier_id: str,
    resolution_option_id: Optional[str] = None,
    notes: Optional[str] = None,
    executed_by: str = "SYSTEM_AGENT",
) -> ExecutionResult:
    """
    Execute a carrier swap on an active or delayed shipment in Supabase PostgreSQL.
    Reassigns carrier_id, resets delay_hours or sets status to IN_TRANSIT,
    creates action record, updates exception to RESOLVED, and logs the audit trail.
    """
    logger.info(f"Executing carrier change: shipment {shipment_id} reassigned to carrier {new_carrier_id}")

    # 1. Idempotency check
    if resolution_option_id and ExceptionQueries.has_action_for_option(resolution_option_id):
        raise RuntimeError(f"Action for resolution option {resolution_option_id} has already been executed.")

    carrier = SupplyChainQueries.get_carrier(new_carrier_id)
    carrier_name = carrier["name"] if carrier else new_carrier_id

    # 2. Execute DB carrier update
    diff = SupplyChainQueries.update_shipment_routing_carrier(
        shipment_id=shipment_id,
        carrier_id=new_carrier_id,
        status="IN_TRANSIT",
        tracking_notes=f"Reassigned to carrier {carrier_name}. Expedited recovery: {notes or 'Mitigating breakdown'}"
    )

    action_id = f"ACT-CAR-{uuid.uuid4().hex[:6].upper()}"
    result_message = (
        f"Successfully changed carrier for shipment {shipment_id} to {carrier_name} ({new_carrier_id}). "
        f"Carrier: {diff['before']['carrier_id']} -> {diff['after']['carrier_id']}. "
        f"Status: {diff['before']['status']} -> {diff['after']['status']}."
    )

    payload = {
        "shipment_id": shipment_id,
        "new_carrier_id": new_carrier_id,
        "notes": notes,
        "state_diff": diff
    }

    # 3. Create action record
    ExceptionQueries.record_action({
        "id": action_id,
        "exception_id": exception_id,
        "resolution_option_id": resolution_option_id,
        "action_type": "CARRIER_CHANGE",
        "executed_by": executed_by,
        "execution_status": "SUCCESS",
        "payload": payload,
        "result_message": result_message
    })

    # 4. Update exception status to RESOLVED
    ExceptionQueries.update_exception_status(
        exception_id=exception_id,
        status="RESOLVED"
    )

    # 5. Create audit log
    _log_audit_step(
        exception_id=exception_id,
        agent_step="ACTION_EXECUTED",
        tool_called="execute_carrier_change",
        input_payload={"shipment_id": shipment_id, "new_carrier_id": new_carrier_id},
        output_payload=diff,
        decision=result_message
    )

    return ExecutionResult(
        action_id=action_id,
        exception_id=exception_id,
        resolution_option_id=resolution_option_id,
        action_type="CARRIER_CHANGE",
        status=ExecutionStatus.SUCCESS,
        result_message=result_message,
        verified_db_changes=diff,
        executed_at=datetime.now(timezone.utc)
    )


def execute_supplier_switch(
    exception_id: str,
    purchase_order_id: str,
    new_supplier_id: str,
    new_delivery_date: Optional[str] = None,
    resolution_option_id: Optional[str] = None,
    notes: Optional[str] = None,
    executed_by: str = "SYSTEM_AGENT",
) -> ExecutionResult:
    """
    Execute a supplier switch on a delayed or at-risk purchase order in Supabase PostgreSQL.
    Reassigns supplier_id, sets status to CONFIRMED, updates expected delivery date,
    creates action record, updates exception to RESOLVED, and logs the audit trail.
    """
    logger.info(f"Executing supplier switch: PO {purchase_order_id} reassigned to supplier {new_supplier_id}")

    # 1. Idempotency check
    if resolution_option_id and ExceptionQueries.has_action_for_option(resolution_option_id):
        raise RuntimeError(f"Action for resolution option {resolution_option_id} has already been executed.")

    # 1b. Resolve real PO if purchase_order_id is fabricated or not found
    po = SupplyChainQueries.get_purchase_order(purchase_order_id)
    if not po:
        supplier_hint = None
        if resolution_option_id:
            opt = ExceptionQueries.get_resolution_option(resolution_option_id)
            if opt and isinstance(opt.get("parameters"), dict):
                supplier_hint = opt["parameters"].get("supplier_id") or opt["parameters"].get("current_supplier_id")
        resolved_po = SupplyChainQueries.resolve_purchase_order(
            po_id_or_number=purchase_order_id,
            supplier_id_or_code=supplier_hint,
            exception_id=exception_id
        )
        if resolved_po:
            logger.info(f"Resolved real purchase order {resolved_po['id']} (replaces placeholder {purchase_order_id})")
            purchase_order_id = resolved_po["id"]
        else:
            raise ValueError(f"Purchase order {purchase_order_id} not found.")

    supplier = SupplyChainQueries.get_supplier(new_supplier_id)
    if not supplier:
        alt_sups = SupplyChainQueries.find_alternative_supplier()
        if not alt_sups:
            raise ValueError(f"Supplier {new_supplier_id} not found and no alternative supplier qualifies.")
        new_supplier_id = alt_sups[0]["id"]
        supplier = SupplyChainQueries.get_supplier(new_supplier_id)
    supplier_name = supplier["name"] if supplier else new_supplier_id

    # 2. Execute DB PO update
    diff = SupplyChainQueries.switch_purchase_order_supplier(
        po_id=purchase_order_id,
        new_supplier_id=new_supplier_id,
        new_delivery_date=new_delivery_date,
        notes=notes or f"Switched to alternative supplier {supplier_name}"
    )

    action_id = f"ACT-SUP-{uuid.uuid4().hex[:6].upper()}"
    result_message = (
        f"Successfully switched supplier for purchase order {purchase_order_id} to {supplier_name} ({new_supplier_id}). "
        f"Supplier: {diff['before']['supplier_id']} -> {diff['after']['supplier_id']}. "
        f"Status: {diff['before']['status']} -> {diff['after']['status']}. "
        f"New expected delivery: {diff['after']['expected_delivery_date']}."
    )

    payload = {
        "purchase_order_id": purchase_order_id,
        "new_supplier_id": new_supplier_id,
        "new_delivery_date": new_delivery_date,
        "notes": notes,
        "state_diff": diff
    }

    # 3. Create action record
    ExceptionQueries.record_action({
        "id": action_id,
        "exception_id": exception_id,
        "resolution_option_id": resolution_option_id,
        "action_type": "SUPPLIER_SWITCH",
        "executed_by": executed_by,
        "execution_status": "SUCCESS",
        "payload": payload,
        "result_message": result_message
    })

    # 4. Update exception status to RESOLVED
    ExceptionQueries.update_exception_status(
        exception_id=exception_id,
        status="RESOLVED"
    )

    # 5. Create audit log
    _log_audit_step(
        exception_id=exception_id,
        agent_step="ACTION_EXECUTED",
        tool_called="execute_supplier_switch",
        input_payload={"purchase_order_id": purchase_order_id, "new_supplier_id": new_supplier_id},
        output_payload=diff,
        decision=result_message
    )

    return ExecutionResult(
        action_id=action_id,
        exception_id=exception_id,
        resolution_option_id=resolution_option_id,
        action_type="SUPPLIER_SWITCH",
        status=ExecutionStatus.SUCCESS,
        result_message=result_message,
        verified_db_changes=diff,
        executed_at=datetime.now(timezone.utc)
    )


def expedite_purchase_order(
    exception_id: str,
    purchase_order_id: str,
    expedited_delivery_date: Optional[str] = None,
    cost_multiplier: float = 1.35,
    resolution_option_id: Optional[str] = None,
    notes: Optional[str] = None,
    executed_by: str = "SYSTEM_AGENT",
) -> ExecutionResult:
    """
    Expedite an existing purchase order in Supabase PostgreSQL.
    Sets is_expedited = TRUE, updates status to EXPEDITED, updates cost and expected delivery date,
    creates action record, updates exception to RESOLVED, and logs the audit trail.
    """
    logger.info(f"Expediting purchase order {purchase_order_id}")

    # 1. Idempotency check
    if resolution_option_id and ExceptionQueries.has_action_for_option(resolution_option_id):
        raise RuntimeError(f"Action for resolution option {resolution_option_id} has already been executed.")

    # 2. Resolve real PO if purchase_order_id is fabricated or not found
    po = SupplyChainQueries.get_purchase_order(purchase_order_id)
    if not po:
        supplier_hint = None
        if resolution_option_id:
            opt = ExceptionQueries.get_resolution_option(resolution_option_id)
            if opt and isinstance(opt.get("parameters"), dict):
                supplier_hint = opt["parameters"].get("supplier_id")
        resolved_po = SupplyChainQueries.resolve_purchase_order(
            po_id_or_number=purchase_order_id,
            supplier_id_or_code=supplier_hint,
            exception_id=exception_id
        )
        if resolved_po:
            logger.info(f"Resolved real purchase order {resolved_po['id']} (replaces placeholder {purchase_order_id})")
            purchase_order_id = resolved_po["id"]
        else:
            raise ValueError(f"Purchase order {purchase_order_id} not found.")

    # 3. Execute DB PO expedite
    diff = SupplyChainQueries.expedite_purchase_order(
        po_id=purchase_order_id,
        expedited_delivery_date=expedited_delivery_date,
        cost_multiplier=cost_multiplier,
        notes=notes or "PO expedited to resolve supply chain exception"
    )

    action_id = f"ACT-EXP-{uuid.uuid4().hex[:6].upper()}"
    result_message = (
        f"Successfully expedited purchase order {purchase_order_id}. "
        f"Cost: ${float(diff['before']['total_cost']):,.2f} -> ${float(diff['after']['total_cost']):,.2f}. "
        f"Status: {diff['before']['status']} -> {diff['after']['status']}. "
        f"Delivery: {diff['before']['expected_delivery_date']} -> {diff['after']['expected_delivery_date']}."
    )

    payload = {
        "purchase_order_id": purchase_order_id,
        "expedited_delivery_date": expedited_delivery_date,
        "cost_multiplier": cost_multiplier,
        "notes": notes,
        "state_diff": diff
    }

    # 3. Create action record
    ExceptionQueries.record_action({
        "id": action_id,
        "exception_id": exception_id,
        "resolution_option_id": resolution_option_id,
        "action_type": "EXPEDITE_PO",
        "executed_by": executed_by,
        "execution_status": "SUCCESS",
        "payload": payload,
        "result_message": result_message
    })

    # 4. Update exception status to RESOLVED
    ExceptionQueries.update_exception_status(
        exception_id=exception_id,
        status="RESOLVED"
    )

    # 5. Create audit log
    _log_audit_step(
        exception_id=exception_id,
        agent_step="ACTION_EXECUTED",
        tool_called="expedite_purchase_order",
        input_payload={"purchase_order_id": purchase_order_id, "cost_multiplier": cost_multiplier},
        output_payload=diff,
        decision=result_message
    )

    return ExecutionResult(
        action_id=action_id,
        exception_id=exception_id,
        resolution_option_id=resolution_option_id,
        action_type="EXPEDITE_PO",
        status=ExecutionStatus.SUCCESS,
        result_message=result_message,
        verified_db_changes=diff,
        executed_at=datetime.now(timezone.utc)
    )


RESOLUTION_EXECUTION_TOOLS = {
    "INVENTORY_TRANSFER": execute_inventory_transfer,
    "SHIPMENT_REROUTE": execute_shipment_reroute,
    "CARRIER_CHANGE": execute_carrier_change,
    "SUPPLIER_SWITCH": execute_supplier_switch,
    "EXPEDITE_PO": expedite_purchase_order,
}


def execute_replenishment_po(
    exception_id: str,
    product_id: str,
    supplier_id: str,
    destination_warehouse_id: str,
    quantity: int,
    unit_cost: Optional[float] = None,
    lead_time_days: Optional[int] = None,
    resolution_option_id: Optional[str] = None,
    notes: Optional[str] = None,
    executed_by: str = "SYSTEM_AGENT",
) -> ExecutionResult:
    """
    Raise a replenishment purchase order to the product's supplier in Supabase PostgreSQL.
    Creates the PO and its line, books the quantity as in-transit stock at the destination,
    records the action, updates the exception to RESOLVED, and logs the audit trail.
    """
    logger.info(f"Raising replenishment PO: {quantity} x {product_id} from {supplier_id} into {destination_warehouse_id}")

    if resolution_option_id and ExceptionQueries.has_action_for_option(resolution_option_id):
        raise RuntimeError(f"Action for resolution option {resolution_option_id} has already been executed.")

    product = SupplyChainQueries.get_product(product_id)
    if not product:
        raise ValueError(f"Product {product_id} not found.")
    supplier = SupplyChainQueries.get_supplier(supplier_id)
    if not supplier:
        raise ValueError(f"Supplier {supplier_id} not found.")
    warehouse = SupplyChainQueries.get_warehouse(destination_warehouse_id)
    if not warehouse:
        raise ValueError(f"Warehouse {destination_warehouse_id} not found.")

    cost = float(unit_cost if unit_cost is not None else (product.get("unit_cost") or 0.0))
    lead = int(lead_time_days if lead_time_days is not None else (supplier.get("lead_time_days") or 7))

    diff = SupplyChainQueries.create_replenishment_po(
        supplier_id=supplier["id"],
        product_id=product["id"],
        destination_warehouse_id=warehouse["id"],
        quantity=int(quantity),
        unit_cost=cost,
        lead_time_days=lead,
        notes=notes or "Replenishment raised to resolve a stock exception",
    )

    action_id = f"ACT-RPL-{uuid.uuid4().hex[:6].upper()}"
    result_message = (
        f"Raised replenishment PO {diff['po_number']} to {supplier['name']} for {diff['quantity']:,} units of "
        f"{product['name']} into {warehouse['name']}. Value ${diff['total_cost']:,.2f}; expected "
        f"{diff['expected_delivery_date'][:10]} ({lead}-day lead time). In-transit stock: "
        f"{diff['in_transit_before']} -> {diff['in_transit_after']}."
    )

    ExceptionQueries.record_action({
        "id": action_id,
        "exception_id": exception_id,
        "resolution_option_id": resolution_option_id,
        "action_type": "REPLENISHMENT_PO",
        "executed_by": executed_by,
        "execution_status": "SUCCESS",
        "payload": {"notes": notes, "state_diff": diff},
        "result_message": result_message,
    })

    ExceptionQueries.update_exception_status(exception_id=exception_id, status="RESOLVED")

    _log_audit_step(
        exception_id=exception_id,
        agent_step="ACTION_EXECUTED",
        tool_called="execute_replenishment_po",
        input_payload={
            "product_id": product["id"],
            "supplier_id": supplier["id"],
            "destination_warehouse_id": warehouse["id"],
            "quantity": int(quantity),
        },
        output_payload=diff,
        decision=result_message,
    )

    return ExecutionResult(
        action_id=action_id,
        exception_id=exception_id,
        resolution_option_id=resolution_option_id,
        action_type="REPLENISHMENT_PO",
        status=ExecutionStatus.SUCCESS,
        result_message=result_message,
        verified_db_changes=diff,
        executed_at=datetime.now(timezone.utc),
    )

RESOLUTION_EXECUTION_TOOLS["REPLENISHMENT_PO"] = execute_replenishment_po
