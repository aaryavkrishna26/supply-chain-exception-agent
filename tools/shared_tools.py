"""
Shared operational tools for orders, products, inventory, and warehouses.
Queries live Supabase PostgreSQL data via SupplyChainQueries.
"""

from typing import Any, Dict, List, Optional
from database.queries.supply_chain import SupplyChainQueries


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve full details for an order including customer information and items.
    Accepts order UUID or order_number (e.g. 'ORD-5002' or 'SO-2024-5002').
    """
    order = SupplyChainQueries.get_order(order_id)
    if not order:
        return None
    # Attach customer tier if available
    customer = SupplyChainQueries.get_customer(order["customer_id"])
    if customer:
        order["customer_name"] = customer["name"]
        order["customer_tier"] = customer["tier"]
        order["customer_sla_hours"] = customer["sla_hours"]
    return order


def get_product(product_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve product specifications, SKU, unit price/cost, and critical level.
    """
    return SupplyChainQueries.get_product(product_id)


def get_inventory(product_id: str, warehouse_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve current inventory levels for a product across all warehouses,
    or at a specific warehouse.
    """
    if warehouse_id:
        all_inv = SupplyChainQueries.get_warehouse_inventory(warehouse_id)
        return [i for i in all_inv if i.get("product_id") == product_id or i.get("sku") == product_id]
    return SupplyChainQueries.get_inventory_for_product(product_id)


def get_warehouse(warehouse_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve warehouse profile, geographic location, city, and active status.
    """
    return SupplyChainQueries.get_warehouse(warehouse_id)


def find_available_inventory(product_id: str, exclude_warehouse_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Find warehouses with surplus/available stock for the requested product.
    Excludes the affected/source warehouse to identify lateral transfer candidates.
    """
    return SupplyChainQueries.find_available_inventory(product_id, exclude_warehouse_id)
