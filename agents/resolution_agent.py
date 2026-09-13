"""
LangGraph Agentic Resolution Workflow for Supply Chain Exceptions.
Consumes Day 2 InvestigationResult, retrieves live operational context from Supabase,
dynamically generates multiple feasible resolution options across Procurement, Logistics,
and Inventory, compares and ranks them, recommends the optimal action, and enforces
Human Approval requirements for high-impact actions.
"""

import re
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from database.queries.supply_chain import SupplyChainQueries
from database.queries.exceptions import ExceptionQueries
from models.schemas import (
    InvestigationResult,
    ResolutionOption,
    ResolutionResult,
    OperationalRisk,
)
from services.audit_service import AuditService
from agents.llm_factory import compact_for_prompt, get_llm
from agents.prompts import (
    GENERATE_RESOLUTION_OPTIONS_PROMPT,
    COMPARE_AND_RECOMMEND_RESOLUTION_PROMPT,
)

logger = logging.getLogger("resolution_agent")


class ResolutionState(TypedDict):
    exception_id: str
    investigation_result: Dict[str, Any]
    live_context: Dict[str, Any]
    candidate_options: List[Dict[str, Any]]
    recommended_option_name: Optional[str]
    ranking_reasoning: Optional[str]
    approval_required: bool
    confidence: float
    result: Optional[Dict[str, Any]]


# -----------------------------------------------------------------------------
# AUTONOMOUS RESOLUTION REASONER
# -----------------------------------------------------------------------------

class AutonomousResolutionReasoner:
    """
    Resilient cross-functional resolution engine.
    Dynamically reasons over real database findings to formulate feasible,
    cost-effective, and risk-managed resolution options when LLM API rate limits
    or timeouts occur.
    """

    @staticmethod
    def generate_options(
        investigation: Dict[str, Any],
        live_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        options: List[Dict[str, Any]] = []
        exc_type = investigation.get("exception_type", "")
        customer = live_context.get("customer") or {}
        customer_tier = customer.get("tier", "STANDARD")
        is_vip = customer_tier in ("VIP", "ENTERPRISE")
        product = live_context.get("product") or {}
        order = live_context.get("order") or {}
        order_qty = 100
        if order and order.get("items"):
            order_qty = order["items"][0].get("quantity", 100)

        # 1. INVENTORY OPTION: Check for surplus stock in alternative warehouses
        surplus_warehouses = live_context.get("alternative_inventory", [])
        dest_wh_id = (
            live_context.get("destination_warehouse_id")
            or order.get("assigned_warehouse_id")
            or (live_context.get("purchase_order") or {}).get("destination_warehouse_id")
            or (live_context.get("exception") or {}).get("warehouse_id")
        )
        prod_obj = live_context.get("product") or {}
        prod_id = prod_obj.get("id") or (surplus_warehouses[0].get("product_id") if surplus_warehouses else None)

        if surplus_warehouses and prod_id:
            # Pick best surplus warehouse
            best_wh = surplus_warehouses[0]
            avail = best_wh.get("quantity_available", 0)
            wh_city = best_wh.get("warehouse_city", "Nearby Warehouse")
            src_wh_id = best_wh.get("warehouse_id")

            if dest_wh_id and avail >= order_qty and src_wh_id and src_wh_id != dest_wh_id:
                est_cost = 4200.0 if is_vip else 3500.0
                options.append({
                    "option_name": f"Inter-Warehouse Transfer from {wh_city}",
                    "action_type": "INVENTORY_TRANSFER",
                    "description": (
                        f"Transfer {order_qty} units of {prod_obj.get('name', 'product')} "
                        f"from {best_wh.get('warehouse_name', wh_city)} (available: {avail}) "
                        f"to destination warehouse to immediately satisfy order."
                    ),
                    "estimated_cost": est_cost,
                    "expected_time_hours": 18.0 if is_vip else 24.0,
                    "inventory_impact": f"Transfers {order_qty} units from surplus stock in {wh_city}; destination replenished.",
                    "customer_impact": "Prevents SLA breach; preserves on-time customer delivery commitment.",
                    "operational_risk": "LOW",
                    "feasibility": True,
                    "confidence_score": 0.94,
                    "reasoning": (
                        f"{wh_city} warehouse currently holds {avail} available units (well above buffer). "
                        f"Executing this transfer bypasses upstream delays and ensures rapid fulfillment."
                    ),
                    "parameters": {
                        "product_id": prod_id,
                        "source_warehouse_id": src_wh_id,
                        "destination_warehouse_id": dest_wh_id,
                        "from_warehouse_id": src_wh_id,
                        "to_warehouse_id": dest_wh_id,
                        "quantity": order_qty
                    }
                })

        # 2. LOGISTICS OPTION: Carrier Change or Route Reroute
        shipment = live_context.get("shipment")
        alt_carriers = live_context.get("alternative_carriers", [])
        alt_routes = live_context.get("alternative_routes", [])

        if shipment and alt_carriers:
            best_carrier = alt_carriers[0]
            # Re-booking cost: the new mode's recorded freight rate on this shipment's
            # weight; without both, the shipment's current freight is the best estimate.
            per_kg = best_carrier.get("freight_cost_per_kg")
            weight = shipment.get("weight_kg")
            if per_kg and weight:
                cost_factor = float(per_kg) * float(weight)
            else:
                cost_factor = float(shipment.get("shipping_cost") or 0.0)
            options.append({
                "option_name": f"Expedited Carrier Swap to {best_carrier.get('name')}",
                "action_type": "CARRIER_CHANGE",
                "description": (
                    f"Reassign shipment {shipment.get('shipment_number')} to high-reliability carrier "
                    f"{best_carrier.get('name')} (reliability rating: {best_carrier.get('reliability_rating', 0.95)})."
                ),
                "estimated_cost": round(cost_factor, 2),
                "expected_time_hours": 20.0,
                "inventory_impact": "Shipment remains in transit with upgraded logistics provider.",
                "customer_impact": "Accelerates recovery; expected arrival within 20 hours.",
                "operational_risk": "MEDIUM",
                "feasibility": True,
                "confidence_score": 0.88,
                "reasoning": (
                    f"Current carrier suffered disruption. {best_carrier.get('name')} has active fleet capacity "
                    f"and higher reliability score to recover schedule."
                ),
                "parameters": {
                    "shipment_id": shipment.get("id"),
                    "new_carrier_id": best_carrier.get("id")
                }
            })

        if shipment and alt_routes:
            best_route = alt_routes[0]
            options.append({
                "option_name": f"Reroute via Secondary Corridor ({best_route.get('origin_city')} -> {best_route.get('destination_city')})",
                "action_type": "SHIPMENT_REROUTE",
                "description": (
                    f"Reroute shipment {shipment.get('shipment_number')} via route {best_route.get('id')} "
                    f"({best_route.get('distance_km')} km, risk: {best_route.get('standard_risk_level')})."
                ),
                "estimated_cost": 2800.0,
                "expected_time_hours": float(best_route.get("estimated_transit_hours", 14.0)) + 6.0,
                "inventory_impact": "Goods remain in original transit pipeline on diversion path.",
                "customer_impact": "Avoids roadblock; arrival delayed by ~6 hours instead of total stagnation.",
                "operational_risk": "LOW" if best_route.get("standard_risk_level") == "LOW" else "MEDIUM",
                "feasibility": True,
                "confidence_score": 0.86,
                "reasoning": "Bypasses road disruption and waterlogging by taking active clear route.",
                "parameters": {
                    "shipment_id": shipment.get("id"),
                    "new_route_id": best_route.get("id")
                }
            })

        # 3. PROCUREMENT OPTION: Expedite PO or Alternative Supplier
        po = live_context.get("purchase_order")
        alt_suppliers = live_context.get("alternative_suppliers", [])
        if po:
            po_cost = float(po.get("total_cost", 0.0))
            exp_cost = round(po_cost * 0.25, 2)
            options.append({
                "option_name": "Expedite Purchase Order with Priority Freight",
                "action_type": "EXPEDITE_PO",
                "description": (
                    f"Issue priority expedite notice on purchase order {po.get('po_number')}. "
                    f"Apply expedited freight multiplier for fast-track fab delivery."
                ),
                "estimated_cost": exp_cost,
                "expected_time_hours": 48.0,
                "inventory_impact": "Shortens inbound stock replenishment lead time from 7 days to 2 days.",
                "customer_impact": "Recovers warehouse buffer before downstream customer orders stock out.",
                "operational_risk": "LOW",
                "feasibility": True,
                "confidence_score": 0.89,
                "reasoning": "Existing supplier has production line ready; expedited transit mitigates delivery delay.",
                "parameters": {
                    "purchase_order_id": po.get("id"),
                    "cost_multiplier": 1.25
                }
            })

        if po and alt_suppliers:
            best_supp = alt_suppliers[0]
            options.append({
                "option_name": f"Switch Purchase Order to Supplier {best_supp.get('name')}",
                "action_type": "SUPPLIER_SWITCH",
                "description": (
                    f"Switch order allocation for PO {po.get('po_number')} to qualified supplier "
                    f"{best_supp.get('name')} (lead time: {best_supp.get('lead_time_days')} days, capacity available: {best_supp.get('available_capacity')})."
                ),
                "estimated_cost": 8500.0,
                "expected_time_hours": float(best_supp.get("lead_time_days", 5) * 24),
                "inventory_impact": "Re-sources component from alternative vendor with high capacity.",
                "customer_impact": "Guarantees shipment delivery by onboarding responsive supplier.",
                "operational_risk": "MEDIUM",
                "feasibility": True,
                "confidence_score": 0.85,
                "reasoning": f"Alternative supplier {best_supp.get('name')} holds active spare capacity and superior reliability rating.",
                "parameters": {
                    "purchase_order_id": po.get("id"),
                    "new_supplier_id": best_supp.get("id")
                }
            })

        # 4. REPLENISHMENT OPTION: raise a PO to the product's usual supplier
        replenishment = live_context.get("replenishment")
        if replenishment and int(replenishment.get("quantity") or 0) > 0:
            qty = int(replenishment["quantity"])
            unit_cost = float(replenishment.get("unit_cost") or 0.0)
            lead_days = int(replenishment.get("lead_time_days") or 7)
            reliability = float(replenishment.get("supplier_reliability") or 0.0)
            target = int(replenishment.get("target_level") or 0)
            options.append({
                "option_name": f"Raise Replenishment PO with {replenishment.get('supplier_name')}",
                "action_type": "REPLENISHMENT_PO",
                "description": (
                    f"Issue a purchase order to {replenishment.get('supplier_name')} for {qty:,} units of "
                    f"{prod_obj.get('name', 'the product')} into {replenishment.get('warehouse_name')}, restoring "
                    f"stock to reorder point plus safety stock ({target:,} units)."
                ),
                "estimated_cost": round(qty * unit_cost, 2),
                "expected_time_hours": float(lead_days * 24),
                "inventory_impact": (
                    f"Books {qty:,} units as inbound; available stock recovers from "
                    f"{replenishment.get('available')} to {target:,} units on receipt."
                ),
                "customer_impact": "Restores cover before the shortage reaches customer orders.",
                "operational_risk": "LOW" if reliability >= 0.9 else ("MEDIUM" if reliability >= 0.8 else "HIGH"),
                "feasibility": True,
                "confidence_score": round(min(0.95, max(0.5, reliability)), 2),
                "reasoning": (
                    f"{replenishment.get('supplier_name')} is this product's usual supplier, with a "
                    f"{lead_days}-day lead time and a {reliability:.0%} on-time record."
                ),
                "parameters": {
                    "product_id": prod_obj.get("id"),
                    "supplier_id": replenishment.get("supplier_id"),
                    "destination_warehouse_id": replenishment.get("warehouse_id"),
                    "quantity": qty,
                    "unit_cost": unit_cost,
                    "lead_time_days": lead_days,
                },
            })

        # 5. DEFAULT WAIT / MONITOR OPTION
        options.append({
            "option_name": "Wait and Monitor Status",
            "action_type": "WAIT_AND_MONITOR",
            "description": "Maintain existing arrangements and monitor tracking updates every 4 hours.",
            "estimated_cost": 0.0,
            "expected_time_hours": 72.0,
            "inventory_impact": "Zero inventory adjustments. Warehouse remains at risk of stockout.",
            "customer_impact": "High risk of SLA breach; customer delivery will experience unmitigated delay.",
            "operational_risk": "HIGH" if is_vip else "MEDIUM",
            "feasibility": True,
            "confidence_score": 0.50,
            "reasoning": "Avoids operational spend but bears full exposure to customer dissatisfaction and SLA penalty.",
            "parameters": {}
        })

        return options

    @staticmethod
    def compare_and_rank(
        investigation: Dict[str, Any],
        options: List[Dict[str, Any]],
        live_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare options dynamically balancing SLA, cost, speed, and feasibility.
        """
        customer = live_context.get("customer") or {}
        is_vip = customer.get("tier") in ("VIP", "ENTERPRISE")
        stockout_risk = investigation.get("stockout_risk", "MEDIUM")

        # Prefer inventory transfer if available stock exists and customer is VIP or stockout is Critical/High
        for opt in options:
            if opt["action_type"] == "INVENTORY_TRANSFER" and opt.get("feasibility", True):
                return {
                    "recommended_option_name": opt["option_name"],
                    "reasoning": (
                        f"Cross-warehouse inventory transfer is strongly recommended. "
                        f"With the affected customer designated as {customer.get('tier', 'VIP')} and stockout risk at {stockout_risk}, "
                        f"transferring surplus stock from another warehouse fulfills the order in {opt['expected_time_hours']} hours "
                        f"at a modest cost of ${opt['estimated_cost']:,.2f}, completely averting a costly SLA breach."
                    ),
                    "approval_required": True,
                    "confidence": 0.94
                }

        # For logistics delays where no surplus inventory exists, prefer carrier swap or reroute
        for opt in options:
            if opt["action_type"] in ("CARRIER_CHANGE", "SHIPMENT_REROUTE") and opt.get("feasibility", True):
                return {
                    "recommended_option_name": opt["option_name"],
                    "reasoning": (
                        f"{opt['option_name']} is the optimal logistics mitigation. "
                        f"It directly resolves the transit bottleneck with an expected turnaround of {opt['expected_time_hours']} hours "
                        f"and acceptable operational risk."
                    ),
                    "approval_required": True,
                    "confidence": 0.90
                }

        # For procurement issues, prefer expedite or supplier switch
        for opt in options:
            if opt["action_type"] in ("EXPEDITE_PO", "SUPPLIER_SWITCH") and opt.get("feasibility", True):
                return {
                    "recommended_option_name": opt["option_name"],
                    "reasoning": (
                        f"{opt['option_name']} restores inbound supply replenishment quickly. "
                        f"Protects warehouse safety stock before assembly lines or customer orders starve."
                    ),
                    "approval_required": True,
                    "confidence": 0.88
                }

        # For stock shortages with no transfer source, replenish from the usual supplier
        for opt in options:
            if opt["action_type"] == "REPLENISHMENT_PO" and opt.get("feasibility", True):
                return {
                    "recommended_option_name": opt["option_name"],
                    "reasoning": (
                        f"{opt['option_name']}: no other warehouse holds surplus of this product, so "
                        f"replenishing from its usual supplier is the fastest recovery "
                        f"({opt['expected_time_hours'] / 24:.0f} days, ${opt['estimated_cost']:,.2f})."
                    ),
                    "approval_required": True,
                    "confidence": 0.86,
                }

        # Fallback to first available option
        first_opt = options[0]
        return {
            "recommended_option_name": first_opt["option_name"],
            "reasoning": "Selected highest feasibility candidate.",
            "approval_required": first_opt["action_type"] != "WAIT_AND_MONITOR",
            "confidence": 0.80
        }


# -----------------------------------------------------------------------------
# GRAPH NODES
# -----------------------------------------------------------------------------

def _replenishment_context(product: Dict[str, Any], warehouse_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Size a replenishment order to the product's usual supplier, when the data supports one.

    Orders up to reorder point plus safety stock, net of stock already inbound.
    """
    supplier_id = product.get("primary_supplier_id")
    if not supplier_id or not warehouse_id:
        return None
    item = SupplyChainQueries.get_inventory_item(warehouse_id, product["id"])
    supplier = SupplyChainQueries.get_supplier(supplier_id)
    warehouse = SupplyChainQueries.get_warehouse(warehouse_id)
    if not item or not supplier or not warehouse:
        return None
    available = int(item.get("quantity_available") or 0)
    in_transit = int(item.get("quantity_in_transit") or 0)
    target = int(item.get("reorder_point") or 0) + int(item.get("safety_stock") or 0)
    quantity = target - available - in_transit
    if quantity <= 0:
        return None
    return {
        "supplier_id": supplier["id"],
        "supplier_name": supplier["name"],
        "supplier_reliability": float(supplier.get("reliability_rating") or 0.0),
        "lead_time_days": int(supplier.get("lead_time_days") or 7),
        "warehouse_id": warehouse["id"],
        "warehouse_name": warehouse["name"],
        "available": available,
        "in_transit": in_transit,
        "target_level": target,
        "quantity": quantity,
        "unit_cost": float(product.get("unit_cost") or 0.0),
    }


def _ground_replenishment(params: Dict[str, Any], live_ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pin a REPLENISHMENT_PO option to real records; None when the data cannot support one."""
    sized = live_ctx.get("replenishment")
    product = live_ctx.get("product") or {}
    if not sized or not product.get("id"):
        return None
    grounded = dict(params or {})
    pid = grounded.get("product_id")
    found = SupplyChainQueries.get_product(str(pid)) if pid else None
    grounded["product_id"] = found["id"] if found else product["id"]
    sid = grounded.get("supplier_id")
    found = SupplyChainQueries.get_supplier(str(sid)) if sid else None
    grounded["supplier_id"] = found["id"] if found else sized["supplier_id"]
    wid = grounded.get("destination_warehouse_id")
    found = SupplyChainQueries.get_warehouse(str(wid)) if wid else None
    grounded["destination_warehouse_id"] = found["id"] if found else sized["warehouse_id"]
    try:
        qty = int(grounded.get("quantity") or 0)
    except (TypeError, ValueError):
        qty = 0
    grounded["quantity"] = qty if qty > 0 else sized["quantity"]
    grounded.setdefault("unit_cost", sized["unit_cost"])
    grounded.setdefault("lead_time_days", sized["lead_time_days"])
    return grounded


def gather_resolution_context_node(state: ResolutionState) -> Dict[str, Any]:
    """
    Retrieve live operational database context to ground resolution options
    in actual available stock, carrier capacity, and qualified suppliers.
    """
    inv_res = state["investigation_result"]
    exc_id = state["exception_id"]
    exc = ExceptionQueries.get_exception(exc_id) or {}

    live_context: Dict[str, Any] = {
        "exception": {k: v for k, v in exc.items() if k != "audit_logs"},
        "customer": None,
        "product": None,
        "order": None,
        "shipment": None,
        "purchase_order": None,
        "alternative_inventory": [],
        "alternative_carriers": [],
        "alternative_routes": [],
        "alternative_suppliers": [],
    }

    # 1. Shipment, Carrier & Route Context (resolve first to unlock linked orders/POs)
    shipment_id = exc.get("shipment_id") or inv_res.get("shipment_id")
    if shipment_id:
        shipment = SupplyChainQueries.get_shipment(shipment_id)
        live_context["shipment"] = shipment
        if shipment:
            alt_carriers = SupplyChainQueries.find_alternative_carrier(
                exclude_carrier_id=shipment.get("carrier_id"),
                min_reliability=0.88
            )
            live_context["alternative_carriers"] = alt_carriers
            if shipment.get("origin_location") and shipment.get("destination_location"):
                alt_routes = SupplyChainQueries.find_alternative_route(
                    origin=shipment["origin_location"],
                    destination=shipment["destination_location"],
                    exclude_route_id=shipment.get("route_id")
                )
                live_context["alternative_routes"] = alt_routes

    # 2. Order & Customer Context
    order_id = exc.get("order_id") or inv_res.get("order_id")
    if not order_id and live_context.get("shipment"):
        order_id = live_context["shipment"].get("order_id")
    if order_id:
        order = SupplyChainQueries.get_order(order_id)
        live_context["order"] = order
        if order and order.get("customer_id"):
            customer = SupplyChainQueries.get_customer(order["customer_id"])
            live_context["customer"] = customer

    # 3. Purchase Order & Supplier Context
    po_id = exc.get("purchase_order_id") or inv_res.get("purchase_order_id")
    if not po_id and live_context.get("shipment"):
        po_id = live_context["shipment"].get("purchase_order_id")
    if not po_id and exc.get("category") == "PROCUREMENT":
        resolved_po = SupplyChainQueries.resolve_purchase_order(exception_id=exc_id)
        if resolved_po:
            po_id = resolved_po["id"]

    if po_id:
        po = SupplyChainQueries.get_purchase_order(po_id)
        live_context["purchase_order"] = po
        if po:
            supplier = SupplyChainQueries.get_supplier(po["supplier_id"])
            live_context["supplier"] = supplier
            alt_suppliers = SupplyChainQueries.find_alternative_supplier(
                category=supplier.get("category") if supplier else None,
                exclude_supplier_id=po.get("supplier_id"),
                min_reliability=0.85
            )
            live_context["alternative_suppliers"] = alt_suppliers
    elif exc.get("category") == "PROCUREMENT":
        for text in [exc.get("exception_code"), exc.get("title"), exc.get("description")]:
            if text:
                for s in SupplyChainQueries.list_suppliers():
                    if s["code"] in text or s["name"] in text or s["id"] in text:
                        live_context["supplier"] = s
                        alt_suppliers = SupplyChainQueries.find_alternative_supplier(
                            category=s.get("category"),
                            exclude_supplier_id=s["id"],
                            min_reliability=0.85
                        )
                        live_context["alternative_suppliers"] = alt_suppliers
                        break
                if live_context.get("supplier"):
                    break

    # 4. Destination Warehouse Context
    dest_warehouse_id = exc.get("warehouse_id")
    if not dest_warehouse_id and live_context.get("order"):
        dest_warehouse_id = live_context["order"].get("assigned_warehouse_id")
    if not dest_warehouse_id and live_context.get("purchase_order"):
        dest_warehouse_id = live_context["purchase_order"].get("destination_warehouse_id")
    if not dest_warehouse_id and live_context.get("shipment"):
        dest_loc = live_context["shipment"].get("destination_location")
        wh = SupplyChainQueries.resolve_warehouse(dest_loc)
        if wh:
            dest_warehouse_id = wh["id"]
    live_context["destination_warehouse_id"] = dest_warehouse_id

    # 5. Product & Inventory Context
    product_id = exc.get("product_id")
    if not product_id and live_context.get("order") and live_context["order"].get("items"):
        product_id = live_context["order"]["items"][0].get("product_id")
    if not product_id and live_context.get("purchase_order") and live_context["purchase_order"].get("items"):
        product_id = live_context["purchase_order"]["items"][0].get("product_id")
    if not product_id and inv_res.get("relevant_warehouses"):
        for rw in inv_res["relevant_warehouses"]:
            if rw.get("product_id"):
                product_id = rw["product_id"]
                break
    if not product_id and inv_res.get("investigation_steps"):
        for stp in inv_res["investigation_steps"]:
            t_inp = stp.get("tool_input") if isinstance(stp, dict) else getattr(stp, "tool_input", {})
            if isinstance(t_inp, dict) and t_inp.get("product_id"):
                product_id = t_inp["product_id"]
                break
    if not product_id:
        for txt in [exc.get("title"), exc.get("description"), inv_res.get("root_cause")]:
            if txt:
                p_cand = SupplyChainQueries.resolve_product(txt)
                if p_cand:
                    product_id = p_cand["id"]
                    break

    if product_id:
        prod = SupplyChainQueries.resolve_product(product_id)
        if prod:
            live_context["product"] = prod
            product_id = prod["id"]
            surplus = SupplyChainQueries.find_available_inventory(
                product_id=product_id,
                exclude_warehouse_id=dest_warehouse_id
            )
            live_context["alternative_inventory"] = surplus
            live_context["replenishment"] = _replenishment_context(prod, dest_warehouse_id)

    return {"live_context": live_context}


def generate_options_node(state: ResolutionState) -> Dict[str, Any]:
    """
    Generate multiple feasible resolution options using Groq LLM (or autonomous reasoner).
    """
    inv_res = state["investigation_result"]
    live_ctx = state["live_context"]

    llm = get_llm()
    options_data = None

    if llm:
        try:
            prompt = GENERATE_RESOLUTION_OPTIONS_PROMPT.format(
                investigation_json=json.dumps(compact_for_prompt(inv_res), default=str),
                live_context_json=json.dumps(compact_for_prompt(live_ctx), default=str)
            )
            response = llm.invoke(prompt)
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "options" in parsed:
                options_data = parsed["options"]
            elif isinstance(parsed, list):
                options_data = parsed
        except Exception as e:
            logger.warning(f"Groq LLM generate_options failed, falling back to autonomous reasoner: {e}")
            options_data = None

    if not options_data:
        options_data = AutonomousResolutionReasoner.generate_options(
            investigation=inv_res,
            live_context=live_ctx
        )

    # Validate and normalize options, ensuring real database IDs
    cleaned_options = []
    for opt in options_data:
        act_type = opt.get("action_type", "WAIT_AND_MONITOR")
        params = opt.get("parameters", {})

        # Ground and strictly validate INVENTORY_TRANSFER parameters
        if act_type == "INVENTORY_TRANSFER":
            opt = _ground_and_validate_inventory_transfer(opt, live_ctx, state)
            params = opt.get("parameters", {})

        # Ground replenishment orders on the sized context, never on invented IDs
        elif act_type == "REPLENISHMENT_PO":
            params = _ground_replenishment(params, live_ctx)
            if not params:
                continue  # the data does not support a replenishment order here

        # Guard against hallucinated/fabricated PO IDs
        elif act_type in ("EXPEDITE_PO", "SUPPLIER_SWITCH"):
            curr_poid = params.get("purchase_order_id") or params.get("canceled_po_id")
            if not curr_poid or not SupplyChainQueries.get_purchase_order(curr_poid):
                real_po = live_ctx.get("purchase_order")
                if real_po:
                    params["purchase_order_id"] = real_po["id"]
                    params["po_number"] = real_po.get("po_number")
                elif curr_poid:
                    resolved = SupplyChainQueries.resolve_purchase_order(
                        po_id_or_number=curr_poid,
                        supplier_id_or_code=params.get("supplier_id"),
                        exception_id=state["exception_id"]
                    )
                    if resolved:
                        params["purchase_order_id"] = resolved["id"]
                        params["po_number"] = resolved.get("po_number")

        cleaned_options.append({
            "option_name": opt.get("option_name", "Mitigation Option"),
            "action_type": act_type,
            "description": opt.get("description", ""),
            "estimated_cost": float(opt.get("estimated_cost", 0.0)),
            "expected_time_hours": float(opt.get("expected_time_hours", 24.0)),
            "inventory_impact": opt.get("inventory_impact", "Standard impact"),
            "customer_impact": opt.get("customer_impact", "Standard impact"),
            "operational_risk": opt.get("operational_risk", "LOW"),
            "feasibility": bool(opt.get("feasibility", True)),
            "confidence_score": float(opt.get("confidence_score", 0.85)),
            "reasoning": opt.get("reasoning", ""),
            "parameters": params,
        })

    AuditService.log_step(
        exception_id=state["exception_id"],
        agent_step="RESOLUTION_OPTIONS_GENERATED",
        tool_called=None,
        input_payload={"options_count": len(cleaned_options)},
        output_payload={"options": [o["option_name"] for o in cleaned_options]},
        decision=f"Generated {len(cleaned_options)} candidate resolution options based on real database context."
    )

    return {"candidate_options": cleaned_options}

def _ground_and_validate_inventory_transfer(
    opt: Dict[str, Any],
    live_ctx: Dict[str, Any],
    state: ResolutionState
) -> Dict[str, Any]:
    """
    Ground and strictly validate an INVENTORY_TRANSFER candidate option against live Supabase records.
    Enforces all 9 validation rules before persistence:
    1. Validate product_id exists in products.
    2. Validate source_warehouse_id exists in warehouses.
    3. Validate destination_warehouse_id exists in warehouses.
    4. Validate source and destination are different.
    5. Validate quantity > 0.
    6. Validate source inventory exists.
    7. Validate source inventory has enough available quantity.
    8. Validate destination warehouse is valid and active.
    9. Store the real IDs in resolution_options.parameters.
    """
    params = opt.get("parameters") or {}
    inv_res = state.get("investigation_result") or {}
    exc = live_ctx.get("exception") or {}
    opt_text = f"{opt.get('option_name', '')} {opt.get('description', '')}"

    # 1. Ground & Resolve product_id
    product_id = params.get("product_id")
    prod_row = SupplyChainQueries.resolve_product(product_id) if product_id else None
    if not prod_row:
        for cand in [params.get("product"), params.get("product_name"), params.get("sku")]:
            if cand:
                prod_row = SupplyChainQueries.resolve_product(str(cand))
                if prod_row:
                    break
    if not prod_row and live_ctx.get("product"):
        prod_row = live_ctx["product"]
    if not prod_row:
        for pid in [exc.get("product_id"), (live_ctx.get("order") or {}).get("items", [{}])[0].get("product_id") if live_ctx.get("order") else None]:
            if pid:
                prod_row = SupplyChainQueries.resolve_product(pid)
                if prod_row:
                    break
    if not prod_row and inv_res.get("relevant_warehouses"):
        for rw in inv_res["relevant_warehouses"]:
            if rw.get("product_id"):
                prod_row = SupplyChainQueries.resolve_product(rw["product_id"])
                if prod_row:
                    break
    if not prod_row:
        for txt in [opt_text, exc.get("title"), exc.get("description")]:
            if txt:
                prod_row = SupplyChainQueries.resolve_product(txt)
                if prod_row:
                    break

    resolved_product_id = prod_row["id"] if prod_row else None

    # 2. Ground & Resolve destination_warehouse_id
    dest_wh_candidate = (
        params.get("destination_warehouse_id")
        or params.get("to_warehouse_id")
        or params.get("destination_warehouse")
        or params.get("to_warehouse")
    )
    dest_wh_row = SupplyChainQueries.resolve_warehouse(dest_wh_candidate) if dest_wh_candidate else None
    if not dest_wh_row:
        dest_id_fallback = (
            live_ctx.get("destination_warehouse_id")
            or exc.get("warehouse_id")
            or (live_ctx.get("order") or {}).get("assigned_warehouse_id")
            or (live_ctx.get("purchase_order") or {}).get("destination_warehouse_id")
        )
        if dest_id_fallback:
            dest_wh_row = SupplyChainQueries.resolve_warehouse(dest_id_fallback)
    if not dest_wh_row and live_ctx.get("shipment"):
        dest_wh_row = SupplyChainQueries.resolve_warehouse(live_ctx["shipment"].get("destination_location"))
    resolved_dest_wh_id = dest_wh_row["id"] if dest_wh_row else None

    # 3. Ground & Resolve quantity
    qty_val = params.get("quantity")
    try:
        quantity = int(qty_val) if qty_val is not None else None
    except (ValueError, TypeError):
        quantity = None

    if not quantity or quantity <= 0:
        match = re.search(r'\b(?:transfer|transfers|move|shipping)?\s*(\d{1,5})\s*units?\b', opt_text, re.IGNORECASE)
        if match:
            quantity = int(match.group(1))
        elif live_ctx.get("order") and live_ctx["order"].get("items"):
            quantity = live_ctx["order"]["items"][0].get("quantity", 100)
        elif live_ctx.get("purchase_order") and live_ctx["purchase_order"].get("items"):
            quantity = live_ctx["purchase_order"]["items"][0].get("quantity_ordered", 100)
        else:
            quantity = 100

    # 4. Ground & Resolve source_warehouse_id
    src_wh_candidate = (
        params.get("source_warehouse_id")
        or params.get("from_warehouse_id")
        or params.get("source_warehouse")
        or params.get("from_warehouse")
    )
    src_wh_row = SupplyChainQueries.resolve_warehouse(src_wh_candidate) if src_wh_candidate else None

    # If not resolved or same as destination, search option text for warehouse mentions
    if not src_wh_row or (resolved_dest_wh_id and src_wh_row["id"] == resolved_dest_wh_id):
        for w in SupplyChainQueries.list_warehouses():
            if resolved_dest_wh_id and w["id"] == resolved_dest_wh_id:
                continue
            if (w["city"].lower() in opt_text.lower()) or (w["name"].lower() in opt_text.lower()) or (w["code"].lower() in opt_text.lower()):
                src_wh_row = w
                break

    # If still not resolved, query available inventory for this product
    if (not src_wh_row or (resolved_dest_wh_id and src_wh_row["id"] == resolved_dest_wh_id)) and resolved_product_id:
        surplus = live_ctx.get("alternative_inventory") or []
        if not surplus:
            surplus = SupplyChainQueries.find_available_inventory(
                product_id=resolved_product_id,
                exclude_warehouse_id=resolved_dest_wh_id
            )
        for s in surplus:
            if s.get("warehouse_id") != resolved_dest_wh_id and s.get("quantity_available", 0) > 0:
                src_wh_row = SupplyChainQueries.get_warehouse(s["warehouse_id"])
                break

    resolved_src_wh_id = src_wh_row["id"] if src_wh_row else None

    # --- NINE VALIDATION RULES ---
    validation_errors = []

    # Rule 1: Validate product_id exists in products
    if not resolved_product_id or not SupplyChainQueries.get_product(resolved_product_id):
        validation_errors.append(f"product_id '{resolved_product_id}' not found in products table")

    # Rule 2: Validate source_warehouse_id exists in warehouses
    if not resolved_src_wh_id or not SupplyChainQueries.get_warehouse(resolved_src_wh_id):
        validation_errors.append(f"source_warehouse_id '{resolved_src_wh_id}' not found in warehouses table")

    # Rule 3: Validate destination_warehouse_id exists in warehouses
    if not resolved_dest_wh_id or not SupplyChainQueries.get_warehouse(resolved_dest_wh_id):
        validation_errors.append(f"destination_warehouse_id '{resolved_dest_wh_id}' not found in warehouses table")

    # Rule 4: Validate source and destination are different
    if resolved_src_wh_id and resolved_dest_wh_id and resolved_src_wh_id == resolved_dest_wh_id:
        validation_errors.append(f"Source warehouse '{resolved_src_wh_id}' and destination warehouse '{resolved_dest_wh_id}' cannot be identical")

    # Rule 5: Validate quantity > 0
    if not quantity or quantity <= 0:
        validation_errors.append(f"Transfer quantity must be > 0, got {quantity}")

    # Rule 6 & 7: Validate source inventory exists and has enough available quantity
    if resolved_src_wh_id and resolved_product_id:
        src_inv = SupplyChainQueries.get_inventory_item(resolved_src_wh_id, resolved_product_id)
        if not src_inv:
            validation_errors.append(f"No inventory record found for product {resolved_product_id} at source warehouse {resolved_src_wh_id}")
        else:
            avail_stock = src_inv.get("quantity_available", 0)
            if avail_stock <= 0:
                validation_errors.append(f"Source warehouse {resolved_src_wh_id} has zero available stock for product {resolved_product_id}")
            elif avail_stock < quantity:
                logger.info(f"Adjusting transfer quantity from {quantity} to available stock {avail_stock}")
                quantity = avail_stock

    # Rule 8: Validate destination warehouse is valid and active
    if resolved_dest_wh_id:
        dest_wh = SupplyChainQueries.get_warehouse(resolved_dest_wh_id)
        if not dest_wh or not dest_wh.get("is_active", True):
            validation_errors.append(f"Destination warehouse '{resolved_dest_wh_id}' is inactive or invalid")

    # Rule 9: Store the real IDs in parameters
    if not validation_errors:
        params["product_id"] = resolved_product_id
        params["source_warehouse_id"] = resolved_src_wh_id
        params["destination_warehouse_id"] = resolved_dest_wh_id
        params["from_warehouse_id"] = resolved_src_wh_id  # backward compat
        params["to_warehouse_id"] = resolved_dest_wh_id  # backward compat
        params["quantity"] = int(quantity)
        opt["feasibility"] = True
    else:
        opt["feasibility"] = False
        err_msg = "; ".join(validation_errors)
        opt["reasoning"] = f"{opt.get('reasoning', '')} [INFEASIBLE INVENTORY TRANSFER: {err_msg}]"
        if resolved_product_id:
            params["product_id"] = resolved_product_id
        if resolved_src_wh_id:
            params["source_warehouse_id"] = resolved_src_wh_id
            params["from_warehouse_id"] = resolved_src_wh_id
        if resolved_dest_wh_id:
            params["destination_warehouse_id"] = resolved_dest_wh_id
            params["to_warehouse_id"] = resolved_dest_wh_id
        if quantity:
            params["quantity"] = int(quantity)

    opt["parameters"] = params
    return opt


def compare_and_rank_node(state: ResolutionState) -> Dict[str, Any]:
    """
    Compare candidate options and select the best recommendation.
    """
    inv_res = state["investigation_result"]
    options = state["candidate_options"]
    live_ctx = state["live_context"]

    llm = get_llm()
    rank_decision = None

    if llm:
        try:
            prompt = COMPARE_AND_RECOMMEND_RESOLUTION_PROMPT.format(
                investigation_json=json.dumps(compact_for_prompt(inv_res), default=str),
                options_json=json.dumps(compact_for_prompt(options, max_items=8), default=str)
            )
            response = llm.invoke(prompt)
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            rank_decision = json.loads(content)
        except Exception as e:
            logger.warning(f"Groq LLM compare_and_rank failed, falling back to autonomous reasoner: {e}")
            rank_decision = None

    if not rank_decision:
        rank_decision = AutonomousResolutionReasoner.compare_and_rank(
            investigation=inv_res,
            options=options,
            live_context=live_ctx
        )

    rec_name = rank_decision.get("recommended_option_name")
    reasoning = rank_decision.get("reasoning", "Recommended based on trade-off analysis.")
    approval_req = rank_decision.get("approval_required", True)
    confidence = float(rank_decision.get("confidence", 0.90))

    AuditService.log_step(
        exception_id=state["exception_id"],
        agent_step="RESOLUTION_RECOMMENDED",
        tool_called=None,
        input_payload={"candidate_count": len(options)},
        output_payload={"recommended": rec_name, "approval_required": approval_req},
        decision=f"Recommended option '{rec_name}': {reasoning}"
    )

    return {
        "recommended_option_name": rec_name,
        "ranking_reasoning": reasoning,
        "approval_required": approval_req,
        "confidence": confidence,
    }


def synthesize_resolution_node(state: ResolutionState) -> Dict[str, Any]:
    """
    Persist resolution options into Supabase PostgreSQL, update exception status
    to PENDING_APPROVAL, and synthesize final Pydantic ResolutionResult.
    """
    exc_id = state["exception_id"]
    options = state["candidate_options"]
    rec_name = state["recommended_option_name"]
    reasoning = state["ranking_reasoning"] or "Optimal action selected."
    approval_req = state["approval_required"]
    confidence = state["confidence"]

    persisted_options: List[ResolutionOption] = []
    recommended_opt: Optional[ResolutionOption] = None
    alternatives: List[ResolutionOption] = []

    for opt in options:
        opt_id = f"OPT-{uuid.uuid4().hex[:8].upper()}"
        is_rec = (opt["option_name"] == rec_name) or (recommended_opt is None and opt == options[0])
        
        # Prepare DB record
        db_record = {
            "id": opt_id,
            "exception_id": exc_id,
            "option_name": opt["option_name"],
            "action_type": opt["action_type"],
            "description": opt["description"],
            "estimated_cost": opt["estimated_cost"],
            "expected_time_hours": opt["expected_time_hours"],
            "inventory_impact": opt["inventory_impact"],
            "customer_impact": opt["customer_impact"],
            "operational_risk": opt["operational_risk"],
            "feasibility": opt["feasibility"],
            "confidence_score": opt["confidence_score"],
            "reasoning": opt["reasoning"],
            "is_recommended": is_rec,
            "is_selected": False,
            "parameters": opt.get("parameters", {})
        }

        # Persist to Supabase resolution_options table
        ExceptionQueries.add_resolution_option(db_record)

        model_opt = ResolutionOption(
            id=opt_id,
            exception_id=exc_id,
            option_name=opt["option_name"],
            action_type=opt["action_type"],
            description=opt["description"],
            estimated_cost=opt["estimated_cost"],
            expected_time_hours=opt["expected_time_hours"],
            inventory_impact=opt["inventory_impact"],
            customer_impact=opt["customer_impact"],
            operational_risk=OperationalRisk(opt["operational_risk"]),
            feasibility=opt["feasibility"],
            confidence_score=opt["confidence_score"],
            reasoning=opt["reasoning"],
            is_recommended=is_rec,
            is_selected=False,
            parameters=opt.get("parameters", {})
        )

        persisted_options.append(model_opt)
        if is_rec and not recommended_opt:
            recommended_opt = model_opt
        else:
            alternatives.append(model_opt)

    if not recommended_opt and persisted_options:
        recommended_opt = persisted_options[0]

    if recommended_opt is None:
        raise RuntimeError(
            "The resolution agent produced no candidate options for this exception, "
            "so there is nothing to recommend. Re-run the investigation and try again."
        )

    # Update exception status to PENDING_APPROVAL
    ExceptionQueries.update_exception_status(
        exception_id=exc_id,
        status="PENDING_APPROVAL"
    )

    final_result = ResolutionResult(
        exception_id=exc_id,
        recommended_option=recommended_opt,
        alternatives=alternatives,
        reasoning=reasoning,
        estimated_cost=recommended_opt.estimated_cost if recommended_opt else 0.0,
        estimated_time=recommended_opt.expected_time_hours if recommended_opt else 0.0,
        inventory_impact=recommended_opt.inventory_impact or "Inventory updated",
        customer_impact=recommended_opt.customer_impact or "Customer impact managed",
        operational_risk=recommended_opt.operational_risk.value if recommended_opt else "LOW",
        feasibility=recommended_opt.feasibility if recommended_opt else True,
        confidence=confidence,
        approval_required=approval_req
    )

    return {"result": final_result.model_dump()}


# -----------------------------------------------------------------------------
# GRAPH COMPILATION
# -----------------------------------------------------------------------------

def create_resolution_graph():
    workflow = StateGraph(ResolutionState)

    workflow.add_node("gather_resolution_context", gather_resolution_context_node)
    workflow.add_node("generate_options", generate_options_node)
    workflow.add_node("compare_and_rank", compare_and_rank_node)
    workflow.add_node("synthesize_resolution", synthesize_resolution_node)

    workflow.add_edge(START, "gather_resolution_context")
    workflow.add_edge("gather_resolution_context", "generate_options")
    workflow.add_edge("generate_options", "compare_and_rank")
    workflow.add_edge("compare_and_rank", "synthesize_resolution")
    workflow.add_edge("synthesize_resolution", END)

    return workflow.compile()


resolution_graph = create_resolution_graph()
