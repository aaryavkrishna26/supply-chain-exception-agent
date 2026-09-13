"""
Unified Tool Registry for Agentic Investigation.
All tools query live Supabase PostgreSQL data.
"""

from typing import Any, Callable, Dict

from tools.shared_tools import (
    get_order,
    get_product,
    get_inventory,
    get_warehouse,
    find_available_inventory,
)
from tools.procurement_tools import (
    get_supplier,
    get_supplier_performance,
    get_purchase_order,
    get_supplier_capacity,
    find_alternative_supplier,
)
from tools.logistics_tools import (
    get_shipment,
    get_carrier,
    get_route,
    get_delivery_status,
    find_alternative_carrier,
    find_alternative_route,
)

from tools.resolution_tools import (
    RESOLUTION_EXECUTION_TOOLS,
    execute_inventory_transfer,
    execute_shipment_reroute,
    execute_carrier_change,
    execute_supplier_switch,
    expedite_purchase_order,
)

INVESTIGATION_TOOLS: Dict[str, Callable[..., Any]] = {
    # Shared
    "get_order": get_order,
    "get_product": get_product,
    "get_inventory": get_inventory,
    "get_warehouse": get_warehouse,
    "find_available_inventory": find_available_inventory,
    # Procurement
    "get_supplier": get_supplier,
    "get_supplier_performance": get_supplier_performance,
    "get_purchase_order": get_purchase_order,
    "get_supplier_capacity": get_supplier_capacity,
    "find_alternative_supplier": find_alternative_supplier,
    # Logistics
    "get_shipment": get_shipment,
    "get_carrier": get_carrier,
    "get_route": get_route,
    "get_delivery_status": get_delivery_status,
    "find_alternative_carrier": find_alternative_carrier,
    "find_alternative_route": find_alternative_route,
}

__all__ = [
    "INVESTIGATION_TOOLS",
    "RESOLUTION_EXECUTION_TOOLS",
    "get_order",
    "get_product",
    "get_inventory",
    "get_warehouse",
    "find_available_inventory",
    "get_supplier",
    "get_supplier_performance",
    "get_purchase_order",
    "get_supplier_capacity",
    "find_alternative_supplier",
    "get_shipment",
    "get_carrier",
    "get_route",
    "get_delivery_status",
    "find_alternative_carrier",
    "find_alternative_route",
    "execute_inventory_transfer",
    "execute_shipment_reroute",
    "execute_carrier_change",
    "execute_supplier_switch",
    "expedite_purchase_order",
]

