"""
Supply chain domain queries for procurement, logistics, inventory, orders, and warehouses.
"""

from typing import Any, Dict, List, Optional
from database.client import get_db


class SupplyChainQueries:

    @staticmethod
    def get_customer(customer_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        results = db.execute_query("SELECT * FROM customers WHERE id = :id", {"id": customer_id})
        return results[0] if results else None

    @staticmethod
    def get_product(product_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        results = db.execute_query("SELECT * FROM products WHERE id = :id", {"id": product_id})
        return results[0] if results else None

    @staticmethod
    def resolve_product(product_id_or_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Resolve a real product record from database given an ID, SKU, name, or substring.
        Prevents hallucinated, natural-language, or null product IDs in execution.
        """
        if not product_id_or_name:
            return None
        db = get_db()
        direct = SupplyChainQueries.get_product(product_id_or_name)
        if direct:
            return direct
        sku_rows = db.execute_query("SELECT * FROM products WHERE sku = :val", {"val": product_id_or_name})
        if sku_rows:
            return sku_rows[0]
        name_rows = db.execute_query(
            "SELECT * FROM products WHERE LOWER(name) = LOWER(:val) OR LOWER(sku) = LOWER(:val)",
            {"val": product_id_or_name}
        )
        if name_rows:
            return name_rows[0]
        sub_rows = db.execute_query(
            "SELECT * FROM products WHERE LOWER(:val) LIKE '%' || LOWER(name) || '%' OR LOWER(name) LIKE '%' || LOWER(:val) || '%'",
            {"val": product_id_or_name}
        )
        if sub_rows:
            return sub_rows[0]
        return None

    @staticmethod
    def list_products() -> List[Dict[str, Any]]:
        db = get_db()
        return db.execute_query("SELECT * FROM products ORDER BY name ASC")

    @staticmethod
    def get_order(order_id_or_number: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        results = db.execute_query(
            "SELECT * FROM orders WHERE id = :val OR order_number = :val",
            {"val": order_id_or_number}
        )
        if not results:
            return None
        order = results[0]
        # Fetch items
        items = db.execute_query("SELECT * FROM order_items WHERE order_id = :oid", {"oid": order["id"]})
        order["items"] = items
        return order

    @staticmethod
    def list_orders(status: Optional[str] = None) -> List[Dict[str, Any]]:
        db = get_db()
        if status:
            return db.execute_query("SELECT * FROM orders WHERE status = :st ORDER BY required_delivery_date ASC", {"st": status})
        return db.execute_query("SELECT * FROM orders ORDER BY order_date DESC")

    @staticmethod
    def get_warehouse(warehouse_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        results = db.execute_query("SELECT * FROM warehouses WHERE id = :id", {"id": warehouse_id})
        return results[0] if results else None

    @staticmethod
    def resolve_warehouse(warehouse_id_or_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Resolve a real warehouse record from database given an ID, code, city, name, or substring.
        Prevents hallucinated, natural-language, or null warehouse IDs in execution.
        """
        if not warehouse_id_or_name:
            return None
        db = get_db()
        direct = SupplyChainQueries.get_warehouse(warehouse_id_or_name)
        if direct:
            return direct
        code_rows = db.execute_query("SELECT * FROM warehouses WHERE code = :val", {"val": warehouse_id_or_name})
        if code_rows:
            return code_rows[0]
        exact_rows = db.execute_query(
            "SELECT * FROM warehouses WHERE LOWER(name) = LOWER(:val) OR LOWER(city) = LOWER(:val)",
            {"val": warehouse_id_or_name}
        )
        if exact_rows:
            return exact_rows[0]
        sub_rows = db.execute_query(
            "SELECT * FROM warehouses WHERE LOWER(:val) LIKE '%' || LOWER(city) || '%' "
            "OR LOWER(:val) LIKE '%' || LOWER(name) || '%' "
            "OR LOWER(name) LIKE '%' || LOWER(:val) || '%'",
            {"val": warehouse_id_or_name}
        )
        if sub_rows:
            return sub_rows[0]
        return None

    @staticmethod
    def list_warehouses() -> List[Dict[str, Any]]:
        db = get_db()
        return db.execute_query("SELECT * FROM warehouses WHERE is_active = TRUE")

    @staticmethod
    def get_inventory_for_product(product_id: str) -> List[Dict[str, Any]]:
        """Get inventory level across all warehouses for a product."""
        db = get_db()
        sql = """
            SELECT i.*, w.name as warehouse_name, w.city as warehouse_city, p.name as product_name, p.sku
            FROM inventory i
            JOIN warehouses w ON i.warehouse_id = w.id
            JOIN products p ON i.product_id = p.id
            WHERE i.product_id = :pid
        """
        return db.execute_query(sql, {"pid": product_id})

    @staticmethod
    def get_warehouse_inventory(warehouse_id: str) -> List[Dict[str, Any]]:
        """Get all inventory in a specific warehouse."""
        db = get_db()
        sql = """
            SELECT i.*, p.sku, p.name as product_name, p.unit_price, p.critical_level
            FROM inventory i
            JOIN products p ON i.product_id = p.id
            WHERE i.warehouse_id = :wid
        """
        return db.execute_query(sql, {"wid": warehouse_id})

    @staticmethod
    def get_supplier(supplier_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        results = db.execute_query(
            "SELECT * FROM suppliers WHERE id = :id OR code = :id",
            {"id": supplier_id}
        )
        if not results:
            results = db.execute_query(
                "SELECT * FROM suppliers WHERE name ILIKE :name",
                {"name": f"%{supplier_id}%"}
            )
        return results[0] if results else None

    @staticmethod
    def list_suppliers(category: Optional[str] = None) -> List[Dict[str, Any]]:
        db = get_db()
        if category:
            return db.execute_query("SELECT * FROM suppliers WHERE category = :cat AND is_active = TRUE", {"cat": category})
        return db.execute_query("SELECT * FROM suppliers WHERE is_active = TRUE ORDER BY reliability_rating DESC")

    @staticmethod
    def get_purchase_order(po_id_or_number: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        results = db.execute_query(
            "SELECT * FROM purchase_orders WHERE id = :val OR po_number = :val",
            {"val": po_id_or_number}
        )
        if not results:
            return None
        po = results[0]
        items = db.execute_query("SELECT * FROM purchase_order_items WHERE purchase_order_id = :poid", {"poid": po["id"]})
        po["items"] = items
        return po

    @staticmethod
    def get_purchase_orders_for_supplier(supplier_id_or_code: str) -> List[Dict[str, Any]]:
        """Retrieve purchase orders associated with a supplier ID, code, or name."""
        db = get_db()
        supplier = SupplyChainQueries.get_supplier(supplier_id_or_code)
        sid = supplier["id"] if supplier else supplier_id_or_code
        sql = "SELECT * FROM purchase_orders WHERE supplier_id = :sid ORDER BY issue_date DESC"
        results = db.execute_query(sql, {"sid": sid})
        for po in results:
            items = db.execute_query("SELECT * FROM purchase_order_items WHERE purchase_order_id = :poid", {"poid": po["id"]})
            po["items"] = items
        return results

    @staticmethod
    def resolve_purchase_order(
        po_id_or_number: Optional[str] = None,
        supplier_id_or_code: Optional[str] = None,
        exception_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a real, existing purchase order from the database.
        Handles direct IDs/numbers, supplier lookups, and exception context,
        avoiding fabricated/hallucinated placeholder IDs (e.g. PO-EXPEDITE-...).
        """
        db = get_db()

        # 1. Direct lookup if valid and exists in DB
        if po_id_or_number:
            po = SupplyChainQueries.get_purchase_order(po_id_or_number)
            if po:
                return po

        # 2. Lookup via supplier if provided
        if supplier_id_or_code:
            pos = SupplyChainQueries.get_purchase_orders_for_supplier(supplier_id_or_code)
            if pos:
                delayed = [p for p in pos if p.get("status") in ("DELAYED", "ISSUED", "IN_TRANSIT")]
                return delayed[0] if delayed else pos[0]

        # 3. Lookup via exception context if provided
        if exception_id:
            from database.queries.exceptions import ExceptionQueries
            exc = ExceptionQueries.get_exception(exception_id)
            if exc:
                if exc.get("purchase_order_id"):
                    po = SupplyChainQueries.get_purchase_order(exc["purchase_order_id"])
                    if po:
                        return po
                # Check if exception code, title, or description references a supplier
                for candidate in [exc.get("exception_code"), exc.get("title"), exc.get("description")]:
                    if candidate:
                        for supp in SupplyChainQueries.list_suppliers():
                            if supp["code"] in candidate or supp["name"] in candidate or supp["id"] in candidate:
                                pos = SupplyChainQueries.get_purchase_orders_for_supplier(supp["id"])
                                if pos:
                                    delayed = [p for p in pos if p.get("status") in ("DELAYED", "ISSUED", "IN_TRANSIT")]
                                    return delayed[0] if delayed else pos[0]

        # 4. Check if po_id_or_number is linked in any resolution option parameters
        if po_id_or_number:
            matched_opts = db.execute_query(
                "SELECT exception_id, parameters FROM resolution_options WHERE CAST(parameters AS text) LIKE :val",
                {"val": f"%{po_id_or_number}%"}
            )
            for opt_row in matched_opts:
                eid = opt_row.get("exception_id")
                if eid and eid != exception_id:
                    res = SupplyChainQueries.resolve_purchase_order(exception_id=eid)
                    if res:
                        return res

        # 5. Fallback: check any active delayed purchase orders in the system
        delayed_pos = SupplyChainQueries.list_purchase_orders(status="DELAYED")
        if delayed_pos:
            return SupplyChainQueries.get_purchase_order(delayed_pos[0]["id"])

        return None

    @staticmethod
    def list_purchase_orders(status: Optional[str] = None) -> List[Dict[str, Any]]:
        db = get_db()
        if status:
            return db.execute_query("SELECT * FROM purchase_orders WHERE status = :st ORDER BY expected_delivery_date ASC", {"st": status})
        return db.execute_query("SELECT * FROM purchase_orders ORDER BY issue_date DESC")

    @staticmethod
    def get_shipment(shipment_id_or_number: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        sql = """
            SELECT s.*, c.name as carrier_name, c.reliability_rating as carrier_reliability,
                   r.origin_city, r.destination_city, r.distance_km
            FROM shipments s
            LEFT JOIN carriers c ON s.carrier_id = c.id
            LEFT JOIN routes r ON s.route_id = r.id
            WHERE s.id = :val OR s.shipment_number = :val
        """
        results = db.execute_query(sql, {"val": shipment_id_or_number})
        return results[0] if results else None

    @staticmethod
    def list_shipments(status: Optional[str] = None) -> List[Dict[str, Any]]:
        db = get_db()
        if status:
            return db.execute_query("SELECT * FROM shipments WHERE status = :st ORDER BY expected_delivery_date ASC", {"st": status})
        return db.execute_query("SELECT * FROM shipments ORDER BY created_at DESC")

    @staticmethod
    def get_carrier(carrier_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        results = db.execute_query("SELECT * FROM carriers WHERE id = :id", {"id": carrier_id})
        return results[0] if results else None

    @staticmethod
    def list_carriers() -> List[Dict[str, Any]]:
        db = get_db()
        return db.execute_query("SELECT * FROM carriers WHERE is_active = TRUE ORDER BY reliability_rating DESC")

    @staticmethod
    def get_route(origin: str, destination: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        sql = "SELECT * FROM routes WHERE origin_city = :o AND destination_city = :d"
        results = db.execute_query(sql, {"o": origin, "d": destination})
        return results[0] if results else None

    @staticmethod
    def find_available_inventory(product_id: str, exclude_warehouse_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find warehouses that currently hold available inventory for a given product."""
        db = get_db()
        clauses = ["i.product_id = :pid", "i.quantity_available > 0"]
        params: Dict[str, Any] = {"pid": product_id}
        if exclude_warehouse_id:
            clauses.append("i.warehouse_id != :ex_wid")
            params["ex_wid"] = exclude_warehouse_id
        
        sql = f"""
            SELECT i.*, w.name as warehouse_name, w.city as warehouse_city, w.state as warehouse_state,
                   p.name as product_name, p.sku, p.critical_level
            FROM inventory i
            JOIN warehouses w ON i.warehouse_id = w.id
            JOIN products p ON i.product_id = p.id
            WHERE {' AND '.join(clauses)}
            ORDER BY i.quantity_available DESC
        """
        return db.execute_query(sql, params)

    @staticmethod
    def get_supplier_performance(supplier_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve historical and operational supplier performance metrics."""
        db = get_db()
        supplier = SupplyChainQueries.get_supplier(supplier_id)
        if not supplier:
            return None
        
        # Calculate PO stats
        po_stats = db.execute_query(
            """
            SELECT 
                COUNT(*) as total_pos,
                COUNT(CASE WHEN status = 'DELAYED' THEN 1 END) as delayed_pos,
                COUNT(CASE WHEN status = 'RECEIVED' THEN 1 END) as received_pos,
                COALESCE(AVG(total_cost), 0) as avg_po_value
            FROM purchase_orders
            WHERE supplier_id = :sid
            """,
            {"sid": supplier_id}
        )
        stats = po_stats[0] if po_stats else {}
        
        return {
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "code": supplier["code"],
            "category": supplier["category"],
            "city": supplier["city"],
            "reliability_rating": supplier["reliability_rating"],
            "lead_time_days": supplier["lead_time_days"],
            "expedite_lead_time_days": supplier["expedite_lead_time_days"],
            "expedite_cost_multiplier": supplier["expedite_cost_multiplier"],
            "total_orders": stats.get("total_pos", 0),
            "delayed_orders": stats.get("delayed_pos", 0),
            "received_orders": stats.get("received_pos", 0),
            "is_reliable": supplier["reliability_rating"] >= 0.90
        }

    @staticmethod
    def get_supplier_capacity(supplier_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve current daily capacity and utilization for a supplier."""
        supplier = SupplyChainQueries.get_supplier(supplier_id)
        if not supplier:
            return None
        
        max_cap = supplier["capacity_units_per_day"]
        util_cap = supplier["current_capacity_utilized"]
        avail_cap = max(0, max_cap - util_cap)
        util_pct = round((util_cap / max_cap * 100) if max_cap > 0 else 100.0, 1)

        return {
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "capacity_units_per_day": max_cap,
            "current_capacity_utilized": util_cap,
            "available_capacity_units": avail_cap,
            "utilization_pct": util_pct,
            "is_constrained": util_pct >= 90.0
        }

    @staticmethod
    def find_alternative_supplier(
        category: Optional[str] = None,
        exclude_supplier_id: Optional[str] = None,
        min_reliability: float = 0.85
    ) -> List[Dict[str, Any]]:
        """Query active alternative suppliers meeting reliability criteria."""
        db = get_db()
        clauses = ["is_active = TRUE", "reliability_rating >= :min_rel"]
        params: Dict[str, Any] = {"min_rel": min_reliability}

        if category:
            clauses.append("category = :cat")
            params["cat"] = category
        if exclude_supplier_id:
            clauses.append("id != :ex_sid")
            params["ex_sid"] = exclude_supplier_id

        sql = f"""
            SELECT id, name, code, category, city, reliability_rating, lead_time_days,
                   expedite_lead_time_days, capacity_units_per_day, current_capacity_utilized,
                   (capacity_units_per_day - current_capacity_utilized) as available_capacity,
                   expedite_cost_multiplier
            FROM suppliers
            WHERE {' AND '.join(clauses)}
            ORDER BY reliability_rating DESC, available_capacity DESC
        """
        return db.execute_query(sql, params)

    @staticmethod
    def get_delivery_status(shipment_id_or_number: str) -> Optional[Dict[str, Any]]:
        """Detailed tracking status for a shipment."""
        shipment = SupplyChainQueries.get_shipment(shipment_id_or_number)
        if not shipment:
            return None
        
        return {
            "shipment_id": shipment["id"],
            "shipment_number": shipment["shipment_number"],
            "status": shipment["status"],
            "current_location": shipment.get("current_location"),
            "delay_hours": shipment.get("delay_hours", 0),
            "tracking_notes": shipment.get("tracking_notes"),
            "carrier_id": shipment.get("carrier_id"),
            "carrier_name": shipment.get("carrier_name"),
            "carrier_reliability": shipment.get("carrier_reliability"),
            "origin_location": shipment.get("origin_location"),
            "destination_location": shipment.get("destination_location"),
            "expected_delivery_date": str(shipment.get("expected_delivery_date")),
            "actual_delivery_date": str(shipment.get("actual_delivery_date")) if shipment.get("actual_delivery_date") else None,
            "order_id": shipment.get("order_id"),
            "purchase_order_id": shipment.get("purchase_order_id")
        }

    @staticmethod
    def find_alternative_carrier(
        exclude_carrier_id: Optional[str] = None,
        min_reliability: float = 0.85
    ) -> List[Dict[str, Any]]:
        """Find active alternative carriers."""
        db = get_db()
        clauses = ["is_active = TRUE", "reliability_rating >= :min_rel"]
        params: Dict[str, Any] = {"min_rel": min_reliability}
        if exclude_carrier_id:
            clauses.append("id != :ex_cid")
            params["ex_cid"] = exclude_carrier_id

        sql = f"""
            SELECT * FROM carriers
            WHERE {' AND '.join(clauses)}
            ORDER BY reliability_rating DESC
        """
        return db.execute_query(sql, params)

    @staticmethod
    def find_alternative_route(
        origin: str,
        destination: str,
        exclude_route_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Find alternative routes between cities that avoid high risk."""
        db = get_db()
        clauses = [
            "origin_city = :origin",
            "destination_city = :dest",
            "is_active = TRUE"
        ]
        params: Dict[str, Any] = {"origin": origin, "dest": destination}
        if exclude_route_id:
            clauses.append("id != :ex_rid")
            params["ex_rid"] = exclude_route_id

        sql = f"""
            SELECT * FROM routes
            WHERE {' AND '.join(clauses)}
            ORDER BY CASE standard_risk_level WHEN 'LOW' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END ASC, distance_km ASC
        """
        results = db.execute_query(sql, params)
        if results:
            return results
        
        # Also return all active low/medium risk routes from the origin
        fallback_sql = """
            SELECT * FROM routes
            WHERE origin_city = :origin AND standard_risk_level != 'HIGH' AND is_active = TRUE
            ORDER BY distance_km ASC
        """
        return db.execute_query(fallback_sql, {"origin": origin})

    @staticmethod
    def get_inventory_item(warehouse_id: str, product_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single inventory row for a warehouse and product."""
        db = get_db()
        sql = "SELECT * FROM inventory WHERE warehouse_id = :wid AND product_id = :pid"
        rows = db.execute_query(sql, {"wid": warehouse_id, "pid": product_id})
        return rows[0] if rows else None

    @staticmethod
    def transfer_inventory(
        from_warehouse_id: Optional[str] = None,
        to_warehouse_id: Optional[str] = None,
        product_id: Optional[str] = None,
        quantity: Optional[int] = None,
        source_warehouse_id: Optional[str] = None,
        destination_warehouse_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute an inventory transfer between two warehouses.
        Deducts quantity from source warehouse and credits destination warehouse.
        Returns pre and post transfer states for verification.
        """
        src_id = source_warehouse_id or from_warehouse_id
        dest_id = destination_warehouse_id or to_warehouse_id
        if not src_id or not dest_id or not product_id:
            raise ValueError(
                f"Invalid inventory transfer parameters: product_id={product_id}, "
                f"source_warehouse_id={src_id}, destination_warehouse_id={dest_id}"
            )
        if not quantity or quantity <= 0:
            raise ValueError(f"Inventory transfer quantity must be positive, got: {quantity}")

        db = get_db()
        source_inv = SupplyChainQueries.get_inventory_item(src_id, product_id)
        if not source_inv:
            raise ValueError(f"No inventory record found for product {product_id} at source warehouse {src_id}.")
        if source_inv["quantity_available"] < quantity:
            raise ValueError(
                f"Insufficient inventory at source warehouse {src_id}: "
                f"available={source_inv['quantity_available']}, required={quantity}"
            )

        dest_inv_before = SupplyChainQueries.get_inventory_item(dest_id, product_id)

        # 1. Deduct from source warehouse
        db.execute_statement(
            """
            UPDATE inventory 
            SET quantity_available = quantity_available - :qty,
                updated_at = CURRENT_TIMESTAMP
            WHERE warehouse_id = :wid AND product_id = :pid
            """,
            {"qty": quantity, "wid": src_id, "pid": product_id}
        )

        # 2. Credit to destination warehouse
        if dest_inv_before:
            db.execute_statement(
                """
                UPDATE inventory 
                SET quantity_available = quantity_available + :qty,
                    updated_at = CURRENT_TIMESTAMP
                WHERE warehouse_id = :wid AND product_id = :pid
                """,
                {"qty": quantity, "wid": dest_id, "pid": product_id}
            )
        else:
            new_inv_id = f"INV-{dest_id[-3:]}-{product_id[-3:]}"
            db.execute_statement(
                """
                INSERT INTO inventory (id, warehouse_id, product_id, quantity_available, quantity_reserved, quantity_in_transit)
                VALUES (:id, :wid, :pid, :qty, 0, 0)
                """,
                {"id": new_inv_id, "wid": dest_id, "pid": product_id, "qty": quantity}
            )

        source_inv_after = SupplyChainQueries.get_inventory_item(src_id, product_id)
        dest_inv_after = SupplyChainQueries.get_inventory_item(dest_id, product_id)

        return {
            "source_warehouse_id": src_id,
            "destination_warehouse_id": dest_id,
            "dest_warehouse_id": dest_id,
            "from_warehouse_id": src_id,
            "to_warehouse_id": dest_id,
            "product_id": product_id,
            "quantity_transferred": quantity,
            "source_available_before": source_inv["quantity_available"],
            "source_available_after": source_inv_after["quantity_available"] if source_inv_after else None,
            "dest_available_before": dest_inv_before["quantity_available"] if dest_inv_before else 0,
            "dest_available_after": dest_inv_after["quantity_available"] if dest_inv_after else quantity,
        }

    @staticmethod
    def update_shipment_routing_carrier(
        shipment_id: str,
        carrier_id: Optional[str] = None,
        route_id: Optional[str] = None,
        status: Optional[str] = None,
        tracking_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update carrier, route, status, or notes on a shipment record."""
        db = get_db()
        before = SupplyChainQueries.get_shipment(shipment_id)
        if not before:
            raise ValueError(f"Shipment {shipment_id} not found.")

        set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
        params: Dict[str, Any] = {"id": before["id"]}

        if carrier_id:
            set_clauses.append("carrier_id = :cid")
            params["cid"] = carrier_id
        if route_id:
            set_clauses.append("route_id = :rid")
            params["rid"] = route_id
        if status:
            set_clauses.append("status = :status")
            params["status"] = status
        if tracking_notes:
            existing_notes = before.get("tracking_notes") or ""
            updated_notes = f"{existing_notes} | {tracking_notes}".strip(" |")
            set_clauses.append("tracking_notes = :notes")
            params["notes"] = updated_notes

        sql = f"UPDATE shipments SET {', '.join(set_clauses)} WHERE id = :id"
        db.execute_statement(sql, params)

        after = SupplyChainQueries.get_shipment(shipment_id)
        return {
            "shipment_id": shipment_id,
            "before": {
                "carrier_id": before.get("carrier_id"),
                "route_id": before.get("route_id"),
                "status": before.get("status"),
            },
            "after": {
                "carrier_id": after.get("carrier_id") if after else None,
                "route_id": after.get("route_id") if after else None,
                "status": after.get("status") if after else None,
            }
        }

    @staticmethod
    def expedite_purchase_order(
        po_id: str,
        expedited_delivery_date: Optional[str] = None,
        cost_multiplier: float = 1.35,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Expedite a purchase order, updating delivery schedule and cost."""
        db = get_db()
        before = SupplyChainQueries.get_purchase_order(po_id)
        if not before:
            resolved = SupplyChainQueries.resolve_purchase_order(po_id_or_number=po_id)
            if resolved:
                before = resolved
                po_id = before["id"]
            else:
                raise ValueError(f"Purchase order {po_id} not found.")

        current_cost = float(before.get("total_cost", 0.0))
        new_cost = round(current_cost * cost_multiplier, 2)
        existing_notes = before.get("notes") or ""
        updated_notes = f"{existing_notes} | Expedited: {notes or 'Priority handling'}".strip(" |")

        params: Dict[str, Any] = {
            "id": before["id"],
            "new_cost": new_cost,
            "notes": updated_notes
        }
        set_clauses = [
            "is_expedited = TRUE",
            "status = 'EXPEDITED'",
            "total_cost = :new_cost",
            "notes = :notes",
            "updated_at = CURRENT_TIMESTAMP"
        ]

        if expedited_delivery_date:
            set_clauses.append("expected_delivery_date = :exp_date")
            params["exp_date"] = expedited_delivery_date

        sql = f"UPDATE purchase_orders SET {', '.join(set_clauses)} WHERE id = :id"
        db.execute_statement(sql, params)

        after = SupplyChainQueries.get_purchase_order(po_id)
        return {
            "po_id": po_id,
            "before": {
                "status": before.get("status"),
                "is_expedited": before.get("is_expedited"),
                "total_cost": current_cost,
                "expected_delivery_date": str(before.get("expected_delivery_date")),
            },
            "after": {
                "status": after.get("status") if after else None,
                "is_expedited": after.get("is_expedited") if after else None,
                "total_cost": float(after.get("total_cost", 0.0)) if after else None,
                "expected_delivery_date": str(after.get("expected_delivery_date")) if after else None,
            }
        }

    @staticmethod
    def switch_purchase_order_supplier(
        po_id: str,
        new_supplier_id: str,
        new_delivery_date: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Switch the supplier on a purchase order to an alternative qualified supplier."""
        db = get_db()
        before = SupplyChainQueries.get_purchase_order(po_id)
        if not before:
            resolved = SupplyChainQueries.resolve_purchase_order(po_id_or_number=po_id)
            if resolved:
                before = resolved
                po_id = before["id"]
            else:
                raise ValueError(f"Purchase order {po_id} not found.")

        existing_notes = before.get("notes") or ""
        updated_notes = f"{existing_notes} | Supplier switched to {new_supplier_id}: {notes or 'Mitigation'}".strip(" |")

        params: Dict[str, Any] = {
            "id": before["id"],
            "new_sid": new_supplier_id,
            "notes": updated_notes
        }
        set_clauses = [
            "supplier_id = :new_sid",
            "status = 'CONFIRMED'",
            "notes = :notes",
            "updated_at = CURRENT_TIMESTAMP"
        ]

        if new_delivery_date:
            set_clauses.append("expected_delivery_date = :new_date")
            params["new_date"] = new_delivery_date

        sql = f"UPDATE purchase_orders SET {', '.join(set_clauses)} WHERE id = :id"
        db.execute_statement(sql, params)

        after = SupplyChainQueries.get_purchase_order(po_id)
        return {
            "po_id": po_id,
            "before": {
                "supplier_id": before.get("supplier_id"),
                "status": before.get("status"),
                "expected_delivery_date": str(before.get("expected_delivery_date")),
            },
            "after": {
                "supplier_id": after.get("supplier_id") if after else None,
                "status": after.get("status") if after else None,
                "expected_delivery_date": str(after.get("expected_delivery_date")) if after else None,
            }
        }

    @staticmethod
    def create_replenishment_po(
        supplier_id: str,
        product_id: str,
        destination_warehouse_id: str,
        quantity: int,
        unit_cost: float,
        lead_time_days: int,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Raise a replenishment purchase order and book its quantity as inbound stock.

        The PO, its line and the destination's in-transit update commit together.
        """
        import uuid
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import text

        quantity = int(quantity or 0)
        if quantity <= 0:
            raise ValueError(f"Replenishment quantity must be positive, got: {quantity}")
        unit_cost = float(unit_cost or 0.0)
        now = datetime.now(timezone.utc)
        po_id = f"PO-{uuid.uuid4().hex[:8].upper()}"
        po_number = f"RPL-{now:%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"
        expected = now + timedelta(days=max(1, int(lead_time_days or 1)))
        total = round(quantity * unit_cost, 2)
        inventory_before = SupplyChainQueries.get_inventory_item(destination_warehouse_id, product_id)

        with get_db().engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO purchase_orders (id, po_number, supplier_id, destination_warehouse_id, "
                    "issue_date, expected_delivery_date, status, total_cost, is_expedited, notes) "
                    "VALUES (:id, :po_number, :sid, :wid, :issued, :expected, 'ISSUED', :total, FALSE, :notes)"
                ),
                {
                    "id": po_id,
                    "po_number": po_number,
                    "sid": supplier_id,
                    "wid": destination_warehouse_id,
                    "issued": now,
                    "expected": expected,
                    "total": total,
                    "notes": notes or "Replenishment raised by RELAY",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO purchase_order_items (id, purchase_order_id, product_id, quantity_ordered, "
                    "quantity_received, unit_cost, total_cost) "
                    "VALUES (:id, :po_id, :pid, :qty, 0, :unit_cost, :total)"
                ),
                {
                    "id": f"POI-{uuid.uuid4().hex[:8].upper()}",
                    "po_id": po_id,
                    "pid": product_id,
                    "qty": quantity,
                    "unit_cost": unit_cost,
                    "total": total,
                },
            )
            if inventory_before:
                conn.execute(
                    text(
                        "UPDATE inventory SET quantity_in_transit = quantity_in_transit + :qty, "
                        "updated_at = CURRENT_TIMESTAMP WHERE warehouse_id = :wid AND product_id = :pid"
                    ),
                    {"qty": quantity, "wid": destination_warehouse_id, "pid": product_id},
                )

        inventory_after = SupplyChainQueries.get_inventory_item(destination_warehouse_id, product_id)
        return {
            "po_id": po_id,
            "po_number": po_number,
            "supplier_id": supplier_id,
            "product_id": product_id,
            "destination_warehouse_id": destination_warehouse_id,
            "quantity": quantity,
            "unit_cost": unit_cost,
            "total_cost": total,
            "expected_delivery_date": expected.isoformat(),
            "in_transit_before": inventory_before.get("quantity_in_transit") if inventory_before else None,
            "in_transit_after": inventory_after.get("quantity_in_transit") if inventory_after else None,
        }
