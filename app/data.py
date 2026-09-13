"""
Cached read layer for the UI.

Every page reads through here so that a single Streamlit rerun never issues the
same Supabase query twice. Writes call `invalidate()` afterwards.

This module only caches; all SQL and business logic stays in `database/` and
`services/`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from database.client import get_db
from database.queries.exceptions import ExceptionQueries
from database.queries.supply_chain import SupplyChainQueries

TTL = 20  # seconds — short enough that operator actions feel live


def invalidate() -> None:
    """Drop every cached read. Call after any write."""
    st.cache_data.clear()


def _rows(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    try:
        return get_db().execute_query(sql, params) or []
    except Exception:
        return []


def _safe(fn, *args, **kwargs) -> List[Dict[str, Any]]:
    try:
        return fn(*args, **kwargs) or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def connection_status() -> Dict[str, Any]:
    try:
        return get_db().test_connection()
    except Exception as err:  # configuration missing, network down, …
        return {"connected": False, "backend": None, "error": str(err)}


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------

@st.cache_data(ttl=TTL, show_spinner=False)
def shipments() -> List[Dict[str, Any]]:
    """Shipments enriched with carrier name and linked PO number."""
    rows = _rows(
        "SELECT s.*, c.name AS carrier_name, c.mode AS carrier_mode, "
        "po.po_number AS po_number "
        "FROM shipments s "
        "LEFT JOIN carriers c ON s.carrier_id = c.id "
        "LEFT JOIN purchase_orders po ON s.purchase_order_id = po.id "
        # Live shipments first (soonest due), then history (most recent first).
        "ORDER BY (s.status IN ('DELIVERED', 'CANCELLED')), "
        "CASE WHEN s.status NOT IN ('DELIVERED', 'CANCELLED') THEN s.expected_delivery_date END ASC, "
        "s.expected_delivery_date DESC"
    )
    return rows if rows else _safe(SupplyChainQueries.list_shipments)


@st.cache_data(ttl=TTL, show_spinner=False)
def purchase_orders() -> List[Dict[str, Any]]:
    """Purchase orders with supplier, destination warehouse and line summary."""
    rows = _rows(
        "SELECT po.*, s.name AS supplier_name, s.code AS supplier_code, "
        "s.city AS supplier_city, s.reliability_rating, "
        "w.name AS warehouse_name, w.city AS warehouse_city, "
        "COALESCE(li.units_ordered, 0) AS units_ordered, COALESCE(li.line_count, 0) AS line_count "
        "FROM purchase_orders po "
        "LEFT JOIN suppliers s ON po.supplier_id = s.id "
        "LEFT JOIN warehouses w ON po.destination_warehouse_id = w.id "
        "LEFT JOIN (SELECT purchase_order_id, SUM(quantity_ordered) AS units_ordered, "
        "COUNT(*) AS line_count FROM purchase_order_items GROUP BY purchase_order_id) li "
        "ON li.purchase_order_id = po.id "
        # Open orders first (soonest due), then history (most recent first).
        "ORDER BY (po.status IN ('RECEIVED', 'CANCELLED')), "
        "CASE WHEN po.status NOT IN ('RECEIVED', 'CANCELLED') THEN po.expected_delivery_date END ASC, "
        "po.expected_delivery_date DESC"
    )
    return rows if rows else _safe(SupplyChainQueries.list_purchase_orders)


@st.cache_data(ttl=TTL, show_spinner=False)
def purchase_order_lines(po_id: str) -> List[Dict[str, Any]]:
    return _rows(
        "SELECT i.*, p.name AS product_name, p.sku "
        "FROM purchase_order_items i "
        "LEFT JOIN products p ON i.product_id = p.id "
        "WHERE i.purchase_order_id = :po_id",
        {"po_id": po_id},
    )


@st.cache_data(ttl=TTL, show_spinner=False)
def inventory() -> List[Dict[str, Any]]:
    return _rows(
        "SELECT i.*, p.name AS product_name, p.sku, p.critical_level, p.unit_cost, p.category, "
        "w.name AS warehouse_name, w.city AS warehouse_city, w.code AS warehouse_code "
        "FROM inventory i "
        "JOIN products p ON i.product_id = p.id "
        "JOIN warehouses w ON i.warehouse_id = w.id "
        "ORDER BY i.quantity_available ASC"
    )


@st.cache_data(ttl=TTL, show_spinner=False)
def product_catalogue() -> List[Dict[str, Any]]:
    """Products with their usual supplier and stock position across the network."""
    return _rows(
        "SELECT p.*, s.name AS supplier_name, s.code AS supplier_code, "
        "s.reliability_rating AS supplier_reliability, s.lead_time_days, "
        "COALESCE(inv.stock_available, 0) AS stock_available, "
        "COALESCE(inv.warehouse_count, 0) AS warehouse_count, "
        "COALESCE(inv.short_lines, 0) AS short_lines, "
        "CASE p.critical_level WHEN 'CRITICAL' THEN 3 WHEN 'HIGH' THEN 2 "
        "WHEN 'MEDIUM' THEN 1 ELSE 0 END AS criticality_rank "
        "FROM products p "
        "LEFT JOIN suppliers s ON p.primary_supplier_id = s.id "
        "LEFT JOIN (SELECT product_id, SUM(quantity_available) AS stock_available, "
        "COUNT(*) AS warehouse_count, "
        "SUM(CASE WHEN quantity_available <= safety_stock THEN 1 ELSE 0 END) AS short_lines "
        "FROM inventory GROUP BY product_id) inv ON inv.product_id = p.id "
        "ORDER BY p.name ASC"
    )


@st.cache_data(ttl=TTL, show_spinner=False)
def suppliers() -> List[Dict[str, Any]]:
    return _safe(SupplyChainQueries.list_suppliers)


@st.cache_data(ttl=TTL, show_spinner=False)
def products() -> List[Dict[str, Any]]:
    return _safe(SupplyChainQueries.list_products)


@st.cache_data(ttl=TTL, show_spinner=False)
def warehouses() -> List[Dict[str, Any]]:
    return _safe(SupplyChainQueries.list_warehouses)


@st.cache_data(ttl=TTL, show_spinner=False)
def carriers() -> List[Dict[str, Any]]:
    return _safe(SupplyChainQueries.list_carriers)


@st.cache_data(ttl=300, show_spinner=False)
def data_sources() -> List[Dict[str, Any]]:
    """Provenance of the loaded operational data (see data/DATA_SOURCES.md)."""
    return _rows("SELECT * FROM data_sources ORDER BY id")


@st.cache_data(ttl=TTL, show_spinner=False)
def orders() -> List[Dict[str, Any]]:
    return _safe(SupplyChainQueries.list_orders)


# ---------------------------------------------------------------------------
# Exception domain
# ---------------------------------------------------------------------------

@st.cache_data(ttl=TTL, show_spinner=False)
def exceptions() -> List[Dict[str, Any]]:
    return _safe(ExceptionQueries.list_exceptions)


@st.cache_data(ttl=TTL, show_spinner=False)
def resolution_options(exception_id: str) -> List[Dict[str, Any]]:
    return _safe(ExceptionQueries.list_resolution_options, exception_id)


def recommended_option(exception_id: str) -> Optional[Dict[str, Any]]:
    options = resolution_options(exception_id)
    for option in options:
        if option.get("is_recommended"):
            return option
    return options[0] if options else None


@st.cache_data(ttl=TTL, show_spinner=False)
def audit_logs(limit: int = 200) -> List[Dict[str, Any]]:
    return _safe(ExceptionQueries.list_all_audit_logs, limit=limit)


@st.cache_data(ttl=TTL, show_spinner=False)
def actions() -> List[Dict[str, Any]]:
    return _rows(
        "SELECT a.*, e.exception_code, e.title AS exception_title "
        "FROM actions a LEFT JOIN exceptions e ON a.exception_id = e.id "
        "ORDER BY a.executed_at DESC"
    )


# ---------------------------------------------------------------------------
# Derived counts used by the navigation and overview tiles
# ---------------------------------------------------------------------------

ACTIVE_EXCEPTION_STATES = ("RESOLVED", "REJECTED", "IGNORED")


def active_exceptions(rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    rows = exceptions() if rows is None else rows
    return [e for e in rows if e.get("status") not in ACTIVE_EXCEPTION_STATES]


def pending_approvals(rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    rows = exceptions() if rows is None else rows
    return [e for e in rows if e.get("status") == "PENDING_APPROVAL"]


def low_stock(rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    rows = inventory() if rows is None else rows
    out = []
    for row in rows:
        try:
            if float(row.get("quantity_available") or 0) <= float(row.get("reorder_point") or 0):
                out.append(row)
        except (TypeError, ValueError):
            continue
    return out


def nav_counts() -> Dict[str, int]:
    """Badge counts shown beside navigation entries."""
    exc = exceptions()
    return {
        "exceptions": len(active_exceptions(exc)),
        "approvals": len(pending_approvals(exc)),
    }
