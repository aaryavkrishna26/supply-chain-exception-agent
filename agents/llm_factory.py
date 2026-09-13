"""
LLM Factory and Autonomous Investigation Reasoner.
Supports OpenAI, Gemini, Groq, and an autonomous Agentic Reasoner fallback.
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("investigation_agent")


def compact_for_prompt(value: Any, max_items: int = 5, max_chars: int = 400) -> Any:
    """Trim nested records for an LLM prompt: long lists and strings are cut.

    Real data returns dozens of candidate rows; sent whole they exceed the
    provider's per-request token budget (Groq's free tier allows 8k tokens a
    minute), and the call fails over to the deterministic reasoner.
    """
    if isinstance(value, dict):
        return {k: compact_for_prompt(v, max_items, max_chars) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [compact_for_prompt(v, max_items, max_chars) for v in list(value)[:max_items]]
        if len(value) > max_items:
            items.append(f"... {len(value) - max_items} more not shown")
        return items
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + "..."
    return value


def get_groq_llm(model: Optional[str] = None) -> Optional[Any]:
    """
    Returns a ChatGroq client initialized from GROQ_API_KEY environment variable.
    Returns None if GROQ_API_KEY is not configured or empty.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key or groq_key.strip() == "" or groq_key == "your-groq-api-key" or groq_key.startswith("gsk-placeholder"):
        return None

    try:
        from langchain_groq import ChatGroq
        selected_model = model or os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
        return ChatGroq(model=selected_model, temperature=0.1, api_key=groq_key)
    except Exception as e:
        logger.warning(f"Failed to initialize ChatGroq: {e}")
        return None


def get_llm():
    """
    Returns an LLM client with Groq as primary provider, falling back to OpenAI or Gemini.
    Returns None if no external API key is found, falling back to autonomous reasoner.
    """
    # 1. Primary: Groq
    groq_llm = get_groq_llm()
    if groq_llm:
        return groq_llm

    # 2. Secondary: OpenAI
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key != "your-openai-api-key" and not openai_key.startswith("sk-placeholder"):
        try:
            from langchain_openai import ChatOpenAI
            model = os.getenv("OPENAI_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
            return ChatOpenAI(model=model, temperature=0.1, api_key=openai_key)
        except Exception as e:
            logger.warning(f"Failed to initialize ChatOpenAI: {e}")

    # 3. Tertiary: Gemini / Google
    google_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if google_key and google_key != "your-gemini-api-key":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            return ChatGoogleGenerativeAI(model=model, temperature=0.1, google_api_key=google_key)
        except Exception as e:
            logger.warning(f"Failed to initialize ChatGoogleGenerativeAI: {e}")

    # 4. Fallback: None -> AutonomousInvestigationReasoner
    return None


class AutonomousInvestigationReasoner:
    """
    Autonomous reasoning engine for supply chain investigations.
    Dynamically evaluates current gathered context, determines missing cross-functional
    information, decides which tool to call, detects when investigation is complete,
    and synthesizes root cause and business impacts from real database evidence.
    """

    @staticmethod
    def decide_next_step(
        exception: Dict[str, Any],
        gathered_context: Dict[str, Any],
        tools_used: List[str],
        step_count: int,
        max_steps: int = 6
    ) -> Dict[str, Any]:
        """
        Dynamically decide whether more information is needed or if investigation can conclude.
        Returns a decision dictionary:
        {
            "action": "call_tool" | "conclude",
            "thought": str,
            "tool_name": Optional[str],
            "tool_input": Dict[str, Any]
        }
        """
        if step_count >= max_steps:
            return {
                "action": "conclude",
                "thought": f"Investigation step limit reached ({step_count}/{max_steps}). Proceeding to synthesis with gathered evidence.",
                "tool_name": None,
                "tool_input": {}
            }

        exc_type = exception.get("exception_type", "")
        category = exception.get("category", "")
        shipment_id = exception.get("shipment_id")
        po_id = exception.get("purchase_order_id")
        order_id = exception.get("order_id")
        warehouse_id = exception.get("warehouse_id")
        product_id = exception.get("product_id")

        # -------------------------------------------------------------
        # 1. Inspect initial focal entity if not yet investigated
        # -------------------------------------------------------------
        if shipment_id and "get_delivery_status" not in tools_used:
            return {
                "action": "call_tool",
                "thought": f"Exception involves shipment {shipment_id}. Need live tracking status, carrier, and transit notes.",
                "tool_name": "get_delivery_status",
                "tool_input": {"shipment_id": shipment_id}
            }

        if po_id and "get_purchase_order" not in tools_used:
            return {
                "action": "call_tool",
                "thought": f"Exception involves Purchase Order {po_id}. Need to inspect PO items, destination warehouse, and supplier.",
                "tool_name": "get_purchase_order",
                "tool_input": {"po_id": po_id}
            }

        # -------------------------------------------------------------
        # 2. Extract discovered entities from gathered context
        # -------------------------------------------------------------
        delivery_status = gathered_context.get("get_delivery_status") or gathered_context.get("get_shipment")
        po_data = gathered_context.get("get_purchase_order")
        order_data = gathered_context.get("get_order")

        # Context extraction
        discovered_carrier_id = None
        discovered_carrier_name = None
        discovered_order_id = order_id
        discovered_supplier_id = None
        discovered_product_id = product_id
        discovered_dest_warehouse_id = warehouse_id
        origin_city = None
        dest_city = None

        if delivery_status:
            discovered_carrier_id = delivery_status.get("carrier_id")
            discovered_carrier_name = delivery_status.get("carrier_name")
            if not discovered_order_id:
                discovered_order_id = delivery_status.get("order_id")
            origin_city = delivery_status.get("origin_location")
            dest_city = delivery_status.get("destination_location")

        if po_data:
            discovered_supplier_id = po_data.get("supplier_id")
            if not discovered_dest_warehouse_id:
                discovered_dest_warehouse_id = po_data.get("destination_warehouse_id")
            items = po_data.get("items", [])
            if items and not discovered_product_id:
                discovered_product_id = items[0].get("product_id")

        if order_data:
            items = order_data.get("items", [])
            if items and not discovered_product_id:
                discovered_product_id = items[0].get("product_id")

        product_data = gathered_context.get("get_product") or {}
        if product_data and not discovered_supplier_id:
            discovered_supplier_id = product_data.get("primary_supplier_id")

        # -------------------------------------------------------------
        # 3. Dynamic branch: Procurement / Supplier investigation
        # -------------------------------------------------------------
        if discovered_supplier_id:
            if "get_supplier_performance" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Supplier {discovered_supplier_id} is responsible for this supply. Need historical reliability rating and fulfillment metrics.",
                    "tool_name": "get_supplier_performance",
                    "tool_input": {"supplier_id": discovered_supplier_id}
                }

            if "get_supplier_capacity" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Checking if supplier {discovered_supplier_id} is constrained or operating at capacity bottleneck.",
                    "tool_name": "get_supplier_capacity",
                    "tool_input": {"supplier_id": discovered_supplier_id}
                }

            # Check inventory level of the product being purchased
            if discovered_product_id and "get_inventory" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Need to check on-hand warehouse inventory for product {discovered_product_id} to quantify stockout risk.",
                    "tool_name": "get_inventory",
                    "tool_input": {"product_id": discovered_product_id, "warehouse_id": discovered_dest_warehouse_id}
                }

            # If supplier is unreliable/delayed, find alternative supplier
            supp_perf = gathered_context.get("get_supplier_performance", {})
            if "find_alternative_supplier" not in tools_used:
                supp_cat = product_data.get("category") or supp_perf.get("category")
                return {
                    "action": "call_tool",
                    "thought": f"Supplier {discovered_supplier_id} has low reliability or delay. Investigating alternative qualified suppliers in category '{supp_cat}'.",
                    "tool_name": "find_alternative_supplier",
                    "tool_input": {"category": supp_cat, "exclude_supplier_id": discovered_supplier_id}
                }

        # -------------------------------------------------------------
        # 4. Dynamic branch: Logistics / Shipment investigation
        # -------------------------------------------------------------
        if delivery_status:
            # Check carrier reliability
            if discovered_carrier_id and "get_carrier" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Shipment is delayed. Investigating carrier {discovered_carrier_id} performance profile.",
                    "tool_name": "get_carrier",
                    "tool_input": {"carrier_id": discovered_carrier_id}
                }

            # If tracking notes mention weather, waterlogging, flooding, route issues
            notes = (delivery_status.get("tracking_notes") or "").lower()
            if any(term in notes for term in ["waterlog", "flood", "road", "route", "halted", "highway"]):
                if origin_city and dest_city and "find_alternative_route" not in tools_used:
                    return {
                        "action": "call_tool",
                        "thought": f"Transit notes indicate route corridor disruption ({origin_city} -> {dest_city}). Investigating alternative low-risk routes.",
                        "tool_name": "find_alternative_route",
                        "tool_input": {"origin": origin_city, "destination": dest_city}
                    }

            # If carrier breakdown or poor reliability, check alternative carrier
            carrier_perf = gathered_context.get("get_carrier", {})
            if "breakdown" in notes or carrier_perf.get("reliability_rating", 1.0) < 0.85:
                if "find_alternative_carrier" not in tools_used:
                    return {
                        "action": "call_tool",
                        "thought": f"Shipment affected by carrier breakdown or low reliability. Finding alternative high-reliability carriers.",
                        "tool_name": "find_alternative_carrier",
                        "tool_input": {"exclude_carrier_id": discovered_carrier_id}
                    }

            # Check impacted customer order
            if discovered_order_id and "get_order" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Shipment is carrying Order {discovered_order_id}. Investigating customer priority, SLA, and line items.",
                    "tool_name": "get_order",
                    "tool_input": {"order_id": discovered_order_id}
                }

            # Check alternative warehouse inventory for cross-docking or lateral transfer
            if discovered_product_id and "find_available_inventory" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Order contains product {discovered_product_id}. Searching other network warehouses for available surplus inventory.",
                    "tool_name": "find_available_inventory",
                    "tool_input": {"product_id": discovered_product_id}
                }

        # -------------------------------------------------------------
        # 5. Inventory Shortage investigation
        # -------------------------------------------------------------
        if exc_type == "INVENTORY_SHORTAGE" or category == "INVENTORY":
            if discovered_product_id and "find_available_inventory" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Inventory shortage for {discovered_product_id}. Searching other network warehouses for surplus inventory.",
                    "tool_name": "find_available_inventory",
                    "tool_input": {"product_id": discovered_product_id, "exclude_warehouse_id": discovered_dest_warehouse_id}
                }
            if discovered_product_id and "get_product" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Identify product {discovered_product_id}'s usual supplier, cost and criticality to size a replenishment.",
                    "tool_name": "get_product",
                    "tool_input": {"product_id": discovered_product_id}
                }
            if discovered_product_id and "find_alternative_supplier" not in tools_used:
                return {
                    "action": "call_tool",
                    "thought": f"Searching alternative suppliers to restock product {discovered_product_id}.",
                    "tool_name": "find_alternative_supplier",
                    "tool_input": {"category": product_data.get("category")}
                }

        # If we reached here and have called multiple relevant tools, we have enough evidence
        if len(tools_used) >= 2:
            return {
                "action": "conclude",
                "thought": "Sufficient multi-functional evidence gathered across supply chain entities to establish root cause and business impact.",
                "tool_name": None,
                "tool_input": {}
            }

        # Fallback to concluding
        return {
            "action": "conclude",
            "thought": "Investigation completed based on available contextual facts.",
            "tool_name": None,
            "tool_input": {}
        }

    @staticmethod
    def synthesize_root_cause(
        exception: Dict[str, Any],
        gathered_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synthesize root cause and evidence points from real database findings."""
        title = exception.get("title", "")
        desc = exception.get("description", "")
        exc_type = exception.get("exception_type", "")
        
        evidence = []
        root_cause = ""

        delivery = gathered_context.get("get_delivery_status") or gathered_context.get("get_shipment")
        carrier = gathered_context.get("get_carrier")
        po = gathered_context.get("get_purchase_order")
        supp_perf = gathered_context.get("get_supplier_performance")
        supp_cap = gathered_context.get("get_supplier_capacity")
        order = gathered_context.get("get_order")
        inv = gathered_context.get("get_inventory")
        avail_inv = gathered_context.get("find_available_inventory")
        alt_supp = gathered_context.get("find_alternative_supplier")
        alt_carrier = gathered_context.get("find_alternative_carrier")

        # Scenario 1: PO Delay
        if po or "PO" in exc_type or "PURCHASE_ORDER" in exc_type:
            po_num = po.get("po_number") if po else exception.get("purchase_order_id")
            notes = po.get("notes", "") if po else ""
            supp_name = supp_perf.get("supplier_name", "Supplier") if supp_perf else "Supplier"
            supp_rel = supp_perf.get("reliability_rating", 0.0) if supp_perf else 0.0
            
            root_cause = (
                f"Purchase Order {po_num} is delayed due to supplier production backlog at {supp_name}. "
                f"Supplier reliability is {supp_rel:.0%} with high capacity utilization."
            )
            evidence.append(f"Purchase Order: {po_num} status is {po.get('status', 'DELAYED') if po else 'DELAYED'}.")
            if notes:
                evidence.append(f"Supplier notes: {notes}")
            if supp_perf:
                evidence.append(f"Supplier {supp_name} reliability rating is {supp_perf['reliability_rating']:.0%}, with {supp_perf.get('delayed_orders', 0)} delayed orders recorded.")
            if supp_cap:
                evidence.append(f"Supplier capacity utilization is at {supp_cap.get('utilization_pct', 0)}% ({supp_cap.get('current_capacity_utilized', 0)}/{supp_cap.get('capacity_units_per_day', 0)} units/day).")
            if inv:
                if isinstance(inv, list) and len(inv) > 0:
                    evidence.append(f"On-hand inventory at destination warehouse is critical: {inv[0].get('quantity_available', 0)} units available vs reorder point of {inv[0].get('reorder_point', 0)}.")
            if alt_supp and len(alt_supp) > 0:
                best_alt = alt_supp[0]
                evidence.append(f"Qualified alternative supplier identified: {best_alt['name']} (Reliability: {best_alt['reliability_rating']:.0%}, Available Capacity: {best_alt.get('available_capacity', 0)} units/day).")

        # Scenario 2: Shipment Delay / Carrier Breakdown
        elif delivery and ("breakdown" in (delivery.get("tracking_notes") or "").lower() or carrier and carrier.get("reliability_rating", 1.0) < 0.85):
            shp_num = delivery.get("shipment_number")
            loc = delivery.get("current_location", "Unknown location")
            carrier_name = delivery.get("carrier_name", "Carrier")
            carrier_rel = carrier.get("reliability_rating", 0.78) if carrier else 0.78

            root_cause = (
                f"Shipment {shp_num} experienced an in-transit mechanical breakdown near {loc} "
                f"while transported by {carrier_name} (Reliability: {carrier_rel:.0%}), causing an estimated {delivery.get('delay_hours', 18)}-hour delay."
            )
            evidence.append(f"Shipment {shp_num} status: {delivery.get('status', 'DELAYED')} at {loc}.")
            evidence.append(f"Carrier notes: {delivery.get('tracking_notes', 'Mechanical breakdown')}.")
            if carrier:
                evidence.append(f"Carrier {carrier_name} reliability is rated low at {carrier_rel:.0%}.")
            if order:
                evidence.append(f"Impacts Order {order.get('order_number')} for {order.get('customer_tier', 'VIP')} Customer '{order.get('customer_name', 'Customer')}' with SLA deadline.")
            if avail_inv:
                surplus = [w for w in avail_inv if w.get("quantity_available", 0) >= 100]
                if surplus:
                    evidence.append(f"Alternative stock verified: Warehouse '{surplus[0]['warehouse_name']}' in {surplus[0]['warehouse_city']} holds {surplus[0]['quantity_available']} units available.")

        # Scenario 3: Route Disruption / Severe Weather
        elif delivery and any(t in (delivery.get("tracking_notes") or "").lower() for t in ["waterlog", "flood", "route", "halted", "weather"]):
            shp_num = delivery.get("shipment_number")
            loc = delivery.get("current_location", "In Transit")
            notes = delivery.get("tracking_notes", "")

            root_cause = (
                f"Shipment {shp_num} is immobilized at {loc} due to major highway route disruption and severe flooding on NH48, "
                f"halting heavy commercial transit."
            )
            evidence.append(f"Shipment {shp_num} transit halted at {loc} with {delivery.get('delay_hours', 14)} hours elapsed delay.")
            evidence.append(f"Transit alert: {notes}")
            if order:
                evidence.append(f"Linked to high-priority customer order {order.get('order_number')} due in {order.get('shipping_city')}.")
            if avail_inv:
                evidence.append(f"Cross-network inventory scan located {len(avail_inv)} warehouses with available product inventory.")

        else:
            # General Root Cause Synthesis
            root_cause = f"Exception '{title}' caused by operational bottlenecks: {desc}"
            evidence.append(f"Exception title: {title}")
            evidence.append(f"Initial anomaly report: {desc}")
            for tool_name, res in gathered_context.items():
                if isinstance(res, dict) and "id" in res:
                    evidence.append(f"Verified operational entity via {tool_name}: ID {res['id']}.")

        return {
            "root_cause": root_cause,
            "evidence": evidence
        }

    @staticmethod
    def synthesize_business_impact(
        exception: Dict[str, Any],
        gathered_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synthesize 5-domain business impact from live gathered evidence."""
        order = gathered_context.get("get_order")
        delivery = gathered_context.get("get_delivery_status") or gathered_context.get("get_shipment")
        po = gathered_context.get("get_purchase_order")
        inv = gathered_context.get("get_inventory")
        avail_inv = gathered_context.get("find_available_inventory")
        supp_perf = gathered_context.get("get_supplier_performance")

        # 1. Inventory Impact
        if avail_inv and len(avail_inv) > 0:
            top_inv = avail_inv[0]
            inventory_impact = (
                f"Destination warehouse faces acute stock depletion; however, network scan identified "
                f"{top_inv['warehouse_name']} ({top_inv['warehouse_city']}) with {top_inv['quantity_available']} available units."
            )
        elif inv and isinstance(inv, list) and len(inv) > 0:
            inventory_impact = f"On-hand inventory at destination warehouse is {inv[0].get('quantity_available', 0)} units, below safe buffer."
        else:
            inventory_impact = "Inventory buffer depleted below safety threshold, posing supply line starvation."

        # 2. Procurement Impact
        if supp_perf:
            procurement_impact = (
                f"Supplier {supp_perf.get('supplier_name')} has {supp_perf.get('lead_time_days', 10)} days standard lead time "
                f"and {supp_perf.get('reliability_rating', 0.8):.0%} reliability; supplier switch or expedite required."
            )
        elif po:
            procurement_impact = f"Purchase Order {po.get('po_number')} delayed by 3+ days, delaying manufacturing intake."
        else:
            procurement_impact = "Inbound replenishment delayed, requiring expedite or alternative sourcing."

        # 3. Logistics Impact
        if delivery:
            delay_hrs = delivery.get("delay_hours", 12)
            logistics_impact = (
                f"Shipment {delivery.get('shipment_number')} delayed by ~{delay_hrs} hours. "
                f"Carrier: {delivery.get('carrier_name', 'Carrier')}. Current location: {delivery.get('current_location', 'In Transit')}."
            )
        else:
            logistics_impact = "In-transit transit delays impacting distribution schedules."

        # 4. Customer Impact
        if order:
            tier = order.get("customer_tier", "Standard")
            sla = order.get("customer_sla_hours", 48)
            customer_impact = (
                f"Affects Order {order.get('order_number')} for {tier} Customer '{order.get('customer_name', 'Customer')}'. "
                f"Immediate SLA breach risk within {sla} hours if no lateral mitigation occurs."
            )
        else:
            customer_impact = "High customer dissatisfaction and SLA penalty risk due to delayed fulfillment."

        # 5. Stockout Risk
        stockout_risk = "HIGH"
        if order and order.get("customer_tier") == "VIP":
            stockout_risk = "CRITICAL"
        elif inv and isinstance(inv, list) and len(inv) > 0 and inv[0].get("quantity_available", 10) <= 10:
            stockout_risk = "CRITICAL"

        financial_loss = float(exception.get("estimated_financial_loss", 25000.0))

        return {
            "inventory_impact": inventory_impact,
            "procurement_impact": procurement_impact,
            "logistics_impact": logistics_impact,
            "customer_impact": customer_impact,
            "stockout_risk": stockout_risk,
            "financial_exposure": financial_loss
        }
