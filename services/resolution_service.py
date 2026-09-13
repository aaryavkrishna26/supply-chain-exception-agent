"""
Resolution Service providing a clean, production-grade interface for
LangGraph-based Resolution Planning, Human-in-the-loop Approval, and
Real Database Operational Execution.
"""

import re
import uuid
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone

from models.schemas import (
    InvestigationResult,
    ResolutionResult,
    ExecutionResult,
    ExecutionStatus,
)
from database.queries.exceptions import ExceptionQueries
from database.queries.supply_chain import SupplyChainQueries
from services.audit_service import AuditService
from tools.resolution_tools import (
    RESOLUTION_EXECUTION_TOOLS,
    execute_inventory_transfer,
    execute_shipment_reroute,
    execute_carrier_change,
    execute_supplier_switch,
    expedite_purchase_order,
    execute_replenishment_po,
)

logger = logging.getLogger("resolution_service")


class ResolutionService:

    @staticmethod
    def plan_resolution(
        investigation_input: Union[str, InvestigationResult, Dict[str, Any]]
    ) -> ResolutionResult:
        """
        Generate multiple feasible resolution options, compare them, and recommend
        the optimal solution based on the investigation findings and live Supabase PostgreSQL data.
        """
        if isinstance(investigation_input, str):
            # Input is exception ID; check if investigation is already done or run it
            exc = ExceptionQueries.get_exception(investigation_input)
            if not exc:
                raise ValueError(f"Exception '{investigation_input}' not found in Supabase.")
            from services.investigation_service import InvestigationService
            inv_result = InvestigationService.investigate(exc["id"])
            investigation_dict = inv_result.model_dump()
            exception_id = exc["id"]
        elif isinstance(investigation_input, InvestigationResult):
            investigation_dict = investigation_input.model_dump()
            exception_id = investigation_input.exception_id
        elif isinstance(investigation_input, dict):
            investigation_dict = investigation_input
            exception_id = investigation_input.get("exception_id")
            if not exception_id:
                raise ValueError("Investigation dictionary missing 'exception_id'.")
        else:
            raise TypeError(f"Unsupported investigation input type: {type(investigation_input)}")

        logger.info(f"Starting resolution planning for exception: {exception_id}")

        initial_state = {
            "exception_id": exception_id,
            "investigation_result": investigation_dict,
            "live_context": {},
            "candidate_options": [],
            "recommended_option_name": None,
            "ranking_reasoning": None,
            "approval_required": True,
            "confidence": 0.88,
            "result": None,
        }

        # Invoke LangGraph resolution workflow
        from agents.resolution_agent import resolution_graph
        final_state = resolution_graph.invoke(initial_state)

        result_dict = final_state.get("result")
        if not result_dict:
            raise RuntimeError("Resolution workflow completed without producing a result.")

        return ResolutionResult.model_validate(result_dict)

    @staticmethod
    def execute_resolution(
        exception_id: str,
        resolution_option_id: str,
        caller: str = "SYSTEM_AGENT"
    ) -> ExecutionResult:
        """
        Attempt to execute a resolution option.
        Enforces the Human-in-the-Loop Approval Gate:
        If the option requires human approval and has not been approved (e.g. status is
        PENDING_APPROVAL, OPEN, or INVESTIGATING, and option is not selected),
        execution is strictly BLOCKED with a PermissionError.
        No operational supply chain data is modified.
        """
        exc = ExceptionQueries.get_exception(exception_id)
        if not exc:
            raise ValueError(f"Exception '{exception_id}' not found in Supabase.")

        opt = ExceptionQueries.get_resolution_option(resolution_option_id)
        if not opt:
            raise ValueError(f"Resolution option '{resolution_option_id}' not found in Supabase.")

        if opt["exception_id"] != exc["id"]:
            raise ValueError(f"Resolution option {resolution_option_id} does not belong to exception {exception_id}.")

        # Enforce Human Approval Gate
        if exc.get("status") != "APPROVED" and not opt.get("is_selected"):
            raise PermissionError(
                f"Execution BLOCKED by Human Approval Gate: Resolution option '{opt['option_name']}' requires explicit human approval. "
                f"Exception '{exception_id}' status is '{exc.get('status')}'. No supply-chain records were altered."
            )

        return ResolutionService.approve_resolution(
            exception_id=exception_id,
            resolution_option_id=resolution_option_id,
            approved_by=caller
        )

    @staticmethod
    def approve_resolution(
        exception_id: str,
        resolution_option_id: str,
        approved_by: str = "HUMAN_OPERATOR",
        override_parameters: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """
        Human Approval Gate & Action Execution.
        Validates the exception and approved resolution option, verifies that the action
        has not already been executed (idempotency), updates database state via execution tools,
        updates exception to RESOLVED, logs an audit entry, and returns structured ExecutionResult.
        """
        logger.info(f"Human approval received for exception {exception_id}, option {resolution_option_id} by {approved_by}")

        exc = ExceptionQueries.get_exception(exception_id)
        if not exc:
            raise ValueError(f"Exception '{exception_id}' not found in Supabase.")

        opt = ExceptionQueries.get_resolution_option(resolution_option_id)
        if not opt:
            raise ValueError(f"Resolution option '{resolution_option_id}' not found in Supabase.")

        if opt["exception_id"] != exc["id"]:
            raise ValueError(f"Resolution option {resolution_option_id} does not belong to exception {exception_id}.")

        if exc.get("status") == "REJECTED":
            raise ValueError(f"Cannot execute resolution for exception '{exception_id}' because it has been REJECTED.")

        # 1. Check for duplicate execution
        if ExceptionQueries.has_action_for_option(resolution_option_id):
            raise RuntimeError(
                f"Action for resolution option {resolution_option_id} has already been executed successfully. Duplicate execution prevented."
            )

        # 2. Mark option as selected and update exception status to APPROVED
        ExceptionQueries.mark_resolution_option_selected(resolution_option_id)
        ExceptionQueries.update_exception_status(
            exception_id=exc["id"],
            status="APPROVED"
        )

        # 3. Record Human Approval Audit Log
        AuditService.log_step(
            exception_id=exc["id"],
            agent_step="HUMAN_APPROVAL",
            tool_called=None,
            input_payload={"resolution_option_id": resolution_option_id, "approved_by": approved_by},
            output_payload={"option_name": opt["option_name"], "action_type": opt["action_type"]},
            decision=f"Option '{opt['option_name']}' approved for execution by {approved_by}.",
            human_approval_status="APPROVED"
        )

        # 4. Dispatch Execution Action
        action_type = opt["action_type"]
        params = opt.get("parameters") or {}
        if override_parameters:
            params.update(override_parameters)

        if action_type == "INVENTORY_TRANSFER":
            src_wh = params.get("source_warehouse_id") or params.get("from_warehouse_id")
            dest_wh = params.get("destination_warehouse_id") or params.get("to_warehouse_id") or exc.get("warehouse_id")
            prod_id = params.get("product_id") or exc.get("product_id")
            qty = params.get("quantity")

            # 1. Defensive Product ID Resolution
            prod_row = SupplyChainQueries.resolve_product(prod_id) if prod_id else None
            if not prod_row:
                # Check order items
                ord_id = exc.get("order_id")
                if not ord_id and exc.get("shipment_id"):
                    shp = SupplyChainQueries.get_shipment(exc["shipment_id"])
                    ord_id = shp.get("order_id") if shp else None
                if ord_id:
                    ord_data = SupplyChainQueries.get_order(ord_id)
                    if ord_data and ord_data.get("items"):
                        prod_row = SupplyChainQueries.resolve_product(ord_data["items"][0]["product_id"])

            if not prod_row and exc.get("purchase_order_id"):
                po_data = SupplyChainQueries.get_purchase_order(exc["purchase_order_id"])
                if po_data and po_data.get("items"):
                    prod_row = SupplyChainQueries.resolve_product(po_data["items"][0]["product_id"])

            if not prod_row:
                for txt in [opt.get("option_name"), opt.get("description"), exc.get("title"), exc.get("description")]:
                    if txt:
                        prod_row = SupplyChainQueries.resolve_product(txt)
                        if prod_row:
                            break

            if prod_row:
                prod_id = prod_row["id"]
            else:
                raise ValueError(f"Unable to resolve real product_id for inventory transfer for exception {exc['id']}.")

            # 2. Defensive Destination Warehouse Resolution
            dest_wh_row = SupplyChainQueries.resolve_warehouse(dest_wh) if dest_wh else None
            if not dest_wh_row:
                dest_id_fallback = exc.get("warehouse_id")
                if not dest_id_fallback and exc.get("order_id"):
                    ord_data = SupplyChainQueries.get_order(exc["order_id"])
                    dest_id_fallback = ord_data.get("assigned_warehouse_id") if ord_data else None
                if dest_id_fallback:
                    dest_wh_row = SupplyChainQueries.resolve_warehouse(dest_id_fallback)
            if not dest_wh_row and exc.get("shipment_id"):
                shp = SupplyChainQueries.get_shipment(exc["shipment_id"])
                if shp and shp.get("destination_location"):
                    dest_wh_row = SupplyChainQueries.resolve_warehouse(shp["destination_location"])
            if not dest_wh_row:
                raise ValueError(
                    f"Unable to resolve a destination warehouse for the inventory transfer on exception {exc['id']}."
                )

            dest_wh = dest_wh_row["id"]

            # 3. Defensive Quantity Resolution
            try:
                qty = int(qty) if qty is not None else None
            except (ValueError, TypeError):
                qty = None

            if not qty or qty <= 0:
                opt_text = f"{opt.get('option_name', '')} {opt.get('description', '')}"
                match = re.search(r'\b(?:transfer|transfers|move|shipping)?\s*(\d{1,5})\s*units?\b', opt_text, re.IGNORECASE)
                if match:
                    qty = int(match.group(1))
                elif exc.get("order_id"):
                    ord_data = SupplyChainQueries.get_order(exc["order_id"])
                    qty = ord_data["items"][0]["quantity"] if (ord_data and ord_data.get("items")) else 100
                else:
                    qty = 100

            # 4. Defensive Source Warehouse Resolution
            src_wh_row = SupplyChainQueries.resolve_warehouse(src_wh) if src_wh else None
            if not src_wh_row or src_wh_row["id"] == dest_wh:
                opt_text = f"{opt.get('option_name', '')} {opt.get('description', '')}"
                for w in SupplyChainQueries.list_warehouses():
                    if w["id"] == dest_wh:
                        continue
                    if (w["city"].lower() in opt_text.lower()) or (w["name"].lower() in opt_text.lower()) or (w["code"].lower() in opt_text.lower()):
                        src_wh_row = w
                        break

            if not src_wh_row or src_wh_row["id"] == dest_wh:
                surplus = SupplyChainQueries.find_available_inventory(
                    product_id=prod_id,
                    exclude_warehouse_id=dest_wh
                )
                for s in surplus:
                    if s.get("warehouse_id") != dest_wh and s.get("quantity_available", 0) > 0:
                        src_wh_row = SupplyChainQueries.get_warehouse(s["warehouse_id"])
                        break

            if not src_wh_row:
                raise ValueError(
                    f"Unable to resolve source warehouse with available inventory for product '{prod_id}' (excluding destination '{dest_wh}')."
                )

            src_wh = src_wh_row["id"]

            # 5. Verify source inventory and available stock
            src_inv = SupplyChainQueries.get_inventory_item(src_wh, prod_id)
            if not src_inv:
                raise ValueError(f"No inventory record found for product {prod_id} at source warehouse {src_wh}.")
            avail_stock = src_inv.get("quantity_available", 0)
            if avail_stock <= 0:
                raise ValueError(f"Source warehouse {src_wh} has 0 available units of product {prod_id}.")
            if avail_stock < qty:
                logger.info(f"Adjusting execution transfer quantity from {qty} to available stock {avail_stock}")
                qty = avail_stock

            # 6. Synchronize resolved parameters to DB
            params["product_id"] = prod_id
            params["source_warehouse_id"] = src_wh
            params["destination_warehouse_id"] = dest_wh
            params["from_warehouse_id"] = src_wh
            params["to_warehouse_id"] = dest_wh
            params["quantity"] = qty
            ExceptionQueries.update_resolution_option_parameters(resolution_option_id, params)

            return execute_inventory_transfer(
                exception_id=exc["id"],
                source_warehouse_id=src_wh,
                destination_warehouse_id=dest_wh,
                product_id=prod_id,
                quantity=qty,
                from_warehouse_id=src_wh,
                to_warehouse_id=dest_wh,
                resolution_option_id=resolution_option_id,
                notes=f"Approved by {approved_by}",
                executed_by=approved_by
            )

        elif action_type == "SHIPMENT_REROUTE":
            shp_id = params.get("shipment_id") or exc.get("shipment_id")
            new_rt = params.get("new_route_id")
            if not new_rt:
                # Find available route
                shp = SupplyChainQueries.get_shipment(shp_id)
                alt_rts = SupplyChainQueries.find_alternative_route(shp["origin_location"], shp["destination_location"]) if shp else []
                if not alt_rts:
                    raise ValueError("No alternative route is recorded for this shipment's lane.")
                new_rt = alt_rts[0]["id"]

            return execute_shipment_reroute(
                exception_id=exc["id"],
                shipment_id=shp_id,
                new_route_id=new_rt,
                resolution_option_id=resolution_option_id,
                notes=f"Approved by {approved_by}",
                executed_by=approved_by
            )

        elif action_type == "CARRIER_CHANGE":
            shp_id = params.get("shipment_id") or exc.get("shipment_id")
            new_car = params.get("new_carrier_id")
            if not new_car:
                alt_cars = SupplyChainQueries.find_alternative_carrier()
                if not alt_cars:
                    raise ValueError("No alternative carrier meets the reliability threshold.")
                new_car = alt_cars[0]["id"]

            return execute_carrier_change(
                exception_id=exc["id"],
                shipment_id=shp_id,
                new_carrier_id=new_car,
                resolution_option_id=resolution_option_id,
                notes=f"Approved by {approved_by}",
                executed_by=approved_by
            )

        elif action_type == "SUPPLIER_SWITCH":
            po_id = params.get("purchase_order_id") or params.get("canceled_po_id") or exc.get("purchase_order_id")
            supplier_hint = params.get("supplier_id") or params.get("current_supplier_id")
            resolved_po = SupplyChainQueries.resolve_purchase_order(
                po_id_or_number=po_id,
                supplier_id_or_code=supplier_hint,
                exception_id=exc["id"]
            )
            if resolved_po:
                po_id = resolved_po["id"]
                params["purchase_order_id"] = po_id
                if "po_number" in resolved_po:
                    params["po_number"] = resolved_po["po_number"]
                ExceptionQueries.update_resolution_option_parameters(resolution_option_id, params)
                if not exc.get("purchase_order_id"):
                    ExceptionQueries.update_exception_purchase_order(exc["id"], po_id)

            new_sup = params.get("new_supplier_id")
            if not new_sup or not SupplyChainQueries.get_supplier(new_sup):
                alt_sups = SupplyChainQueries.find_alternative_supplier()
                if not alt_sups:
                    raise ValueError("No alternative supplier meets the reliability threshold.")
                new_sup = alt_sups[0]["id"]
            else:
                real_sup = SupplyChainQueries.get_supplier(new_sup)
                if real_sup:
                    new_sup = real_sup["id"]

            return execute_supplier_switch(
                exception_id=exc["id"],
                purchase_order_id=po_id,
                new_supplier_id=new_sup,
                resolution_option_id=resolution_option_id,
                notes=f"Approved by {approved_by}",
                executed_by=approved_by
            )

        elif action_type == "EXPEDITE_PO":
            po_id = params.get("purchase_order_id") or exc.get("purchase_order_id")
            supplier_hint = params.get("supplier_id")
            resolved_po = SupplyChainQueries.resolve_purchase_order(
                po_id_or_number=po_id,
                supplier_id_or_code=supplier_hint,
                exception_id=exc["id"]
            )
            if resolved_po:
                po_id = resolved_po["id"]
                params["purchase_order_id"] = po_id
                if "po_number" in resolved_po:
                    params["po_number"] = resolved_po["po_number"]
                ExceptionQueries.update_resolution_option_parameters(resolution_option_id, params)
                if not exc.get("purchase_order_id"):
                    ExceptionQueries.update_exception_purchase_order(exc["id"], po_id)

            multiplier = float(params.get("cost_multiplier", 1.25))

            return expedite_purchase_order(
                exception_id=exc["id"],
                purchase_order_id=po_id,
                cost_multiplier=multiplier,
                resolution_option_id=resolution_option_id,
                notes=f"Approved by {approved_by}",
                executed_by=approved_by
            )

        elif action_type == "REPLENISHMENT_PO":
            prod_row = SupplyChainQueries.resolve_product(params.get("product_id") or exc.get("product_id"))
            if not prod_row:
                raise ValueError(f"Unable to resolve the product to replenish for exception {exc['id']}.")
            wh_row = SupplyChainQueries.resolve_warehouse(
                params.get("destination_warehouse_id") or exc.get("warehouse_id")
            )
            if not wh_row:
                raise ValueError(f"Unable to resolve the destination warehouse for exception {exc['id']}.")
            supplier_ref = params.get("supplier_id") or prod_row.get("primary_supplier_id")
            supplier_row = SupplyChainQueries.get_supplier(supplier_ref) if supplier_ref else None
            if not supplier_row:
                raise ValueError(f"Product {prod_row['id']} has no supplier on record to replenish from.")

            try:
                qty = int(params.get("quantity") or 0)
            except (TypeError, ValueError):
                qty = 0
            if qty <= 0:
                item = SupplyChainQueries.get_inventory_item(wh_row["id"], prod_row["id"]) or {}
                qty = (
                    int(item.get("reorder_point") or 0)
                    + int(item.get("safety_stock") or 0)
                    - int(item.get("quantity_available") or 0)
                    - int(item.get("quantity_in_transit") or 0)
                )
            if qty <= 0:
                raise ValueError("Stock is already at or above its reorder target; nothing to replenish.")

            params.update({
                "product_id": prod_row["id"],
                "destination_warehouse_id": wh_row["id"],
                "supplier_id": supplier_row["id"],
                "quantity": qty,
            })
            ExceptionQueries.update_resolution_option_parameters(resolution_option_id, params)

            return execute_replenishment_po(
                exception_id=exc["id"],
                product_id=prod_row["id"],
                supplier_id=supplier_row["id"],
                destination_warehouse_id=wh_row["id"],
                quantity=qty,
                unit_cost=params.get("unit_cost"),
                lead_time_days=params.get("lead_time_days"),
                resolution_option_id=resolution_option_id,
                notes=f"Approved by {approved_by}",
                executed_by=approved_by,
            )

        elif action_type == "WAIT_AND_MONITOR":
            action_id = f"ACT-WAT-{uuid.uuid4().hex[:6].upper()}"
            result_msg = f"Wait & monitor option approved by {approved_by}. System monitoring active."
            ExceptionQueries.record_action({
                "id": action_id,
                "exception_id": exc["id"],
                "resolution_option_id": resolution_option_id,
                "action_type": "WAIT_AND_MONITOR",
                "executed_by": approved_by,
                "execution_status": "SUCCESS",
                "payload": params,
                "result_message": result_msg
            })
            ExceptionQueries.update_exception_status(
                exception_id=exc["id"],
                status="RESOLVED"
            )
            AuditService.log_step(
                exception_id=exc["id"],
                agent_step="ACTION_EXECUTED",
                tool_called="wait_and_monitor",
                input_payload=params,
                output_payload={"status": "MONITORING"},
                decision=result_msg
            )
            return ExecutionResult(
                action_id=action_id,
                exception_id=exc["id"],
                resolution_option_id=resolution_option_id,
                action_type="WAIT_AND_MONITOR",
                status=ExecutionStatus.SUCCESS,
                result_message=result_msg,
                verified_db_changes={"monitoring_started": True},
                executed_at=datetime.now(timezone.utc)
            )

        else:
            raise ValueError(f"Unknown or unsupported action type: {action_type}")

    @staticmethod
    def reject_resolution(
        exception_id: str,
        resolution_option_id: Optional[str] = None,
        rejected_by: str = "HUMAN_OPERATOR",
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Human Rejection Gate.
        Marks exception as REJECTED and logs rejection reason.
        CRITICAL: Does NOT modify any operational supply chain tables (inventory, shipments, POs).
        """
        logger.info(f"Human rejection for exception {exception_id} by {rejected_by}: {reason}")

        exc = ExceptionQueries.get_exception(exception_id)
        if not exc:
            raise ValueError(f"Exception '{exception_id}' not found in Supabase.")

        ExceptionQueries.update_exception_status(
            exception_id=exc["id"],
            status="REJECTED"
        )

        AuditService.log_step(
            exception_id=exc["id"],
            agent_step="HUMAN_REJECTION",
            tool_called=None,
            input_payload={"resolution_option_id": resolution_option_id, "rejected_by": rejected_by, "reason": reason},
            output_payload={"status": "REJECTED"},
            decision=f"Resolution rejected by {rejected_by}. Reason: {reason or 'User decision'}. No database entities were modified.",
            human_approval_status="REJECTED",
            notes=reason
        )

        return {
            "exception_id": exc["id"],
            "resolution_option_id": resolution_option_id,
            "status": "REJECTED",
            "rejected_by": rejected_by,
            "reason": reason or "User rejected resolution option.",
            "operational_data_modified": False
        }

    @staticmethod
    def get_resolution_options(exception_id: str) -> List[Dict[str, Any]]:
        """Retrieve all generated resolution options for an exception."""
        return ExceptionQueries.list_resolution_options(exception_id)
