"""
Procurement domain investigation tools.
Queries live Supabase PostgreSQL data via SupplyChainQueries.
"""

from typing import Any, Dict, List, Optional
from database.queries.supply_chain import SupplyChainQueries


def get_supplier(supplier_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve supplier profile, contact info, lead time, and reliability metrics.
    """
    return SupplyChainQueries.get_supplier(supplier_id)


def get_supplier_performance(supplier_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve supplier historical performance metrics including reliability rating,
    lead times, expedite multiplier, and past order fulfillment statistics.
    """
    return SupplyChainQueries.get_supplier_performance(supplier_id)


def get_purchase_order(po_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve purchase order details, destination warehouse, line items,
    expected delivery date, and current status.
    Accepts PO UUID or po_number (e.g. 'PO-1001' or 'PO-2024-001').
    """
    po = SupplyChainQueries.get_purchase_order(po_id)
    if not po:
        return None
    # Attach supplier name if available
    supplier = SupplyChainQueries.get_supplier(po["supplier_id"])
    if supplier:
        po["supplier_name"] = supplier["name"]
        po["supplier_reliability"] = supplier["reliability_rating"]
    return po


def get_supplier_capacity(supplier_id: str) -> Optional[Dict[str, Any]]:
    """
    Check supplier daily capacity, current utilization, and remaining available capacity.
    Identifies if supplier is experiencing manufacturing bottleneck.
    """
    return SupplyChainQueries.get_supplier_capacity(supplier_id)


def find_alternative_supplier(
    category: Optional[str] = None,
    exclude_supplier_id: Optional[str] = None,
    min_reliability: float = 0.85
) -> List[Dict[str, Any]]:
    """
    Find active alternative suppliers for a given category with sufficient capacity
    and reliability rating exceeding the threshold.
    """
    return SupplyChainQueries.find_alternative_supplier(
        category=category,
        exclude_supplier_id=exclude_supplier_id,
        min_reliability=min_reliability
    )
