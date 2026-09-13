"""
Supplier workspace: incoming purchase orders, the product catalogue, outbound
shipments, shared exception records and delivery performance.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import streamlit as st

from app import charts, data
from app.pages.exceptions import render_exceptions_page
from app.pages.profile import render_profile_page
from app.shell import goto, render_account_bar, render_sidebar
from app.ui import (
    Col,
    badge,
    callout,
    card_container,
    data_table,
    delay_label,
    detail_grid,
    divider,
    empty_state,
    format_currency,
    format_date,
    format_number,
    format_percent,
    kpi_row,
    list_controls,
    meter,
    mono,
    page_header,
    section,
    spacer,
    title_case,
)
from database.client import get_db

ROLE = "SUPPLIER"

TABLE_LIMIT = 150  # rows rendered per table; search narrows the rest
ACTIVE_SHIPMENT_STATES = ("CREATED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELAYED", "REROUTED", "EXCEPTION")
OPEN_PO_STATES = ("ISSUED", "CONFIRMED", "IN_TRANSIT", "DELAYED", "EXPEDITED")


def _shown(pool: List[Dict[str, Any]]) -> str:
    return f"{min(len(pool), TABLE_LIMIT):,} of {len(pool):,} shown"


def _truncation_note(pool: List[Dict[str, Any]]) -> None:
    if len(pool) > TABLE_LIMIT:
        st.caption(f"Showing the first {TABLE_LIMIT}. Search to narrow the list.")


def render_supplier_app() -> None:
    page = render_sidebar(ROLE)
    render_account_bar(ROLE, page)
    if page == "dashboard":
        _overview()
    elif page == "purchase_orders":
        _purchase_orders()
    elif page == "shipments":
        _shipments()
    elif page == "exceptions":
        render_exceptions_page(ROLE)
    elif page == "products":
        _products()
    elif page == "performance":
        _performance()
    elif page == "profile":
        render_profile_page(ROLE)


# ---------------------------------------------------------------------------
# Account scoping
# ---------------------------------------------------------------------------

def _linked_supplier() -> Optional[Dict[str, Any]]:
    """Match the signed-in user to a supplier record by contact email."""
    email = str(st.session_state.get("user_email") or "").strip().lower()
    if not email:
        return None
    for supplier in data.suppliers():
        if str(supplier.get("contact_email") or "").strip().lower() == email:
            return supplier
    return None


def _scoped_pos(supplier: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = data.purchase_orders()
    if supplier:
        return [p for p in rows if p.get("supplier_id") == supplier.get("id")]
    return rows


def _scope_note(supplier: Optional[Dict[str, Any]]) -> None:
    if supplier:
        st.caption(
            f"Scoped to {supplier.get('name')} ({supplier.get('code')}) — "
            f"matched on your account email."
        )
    else:
        st.caption(
            "Your account is not linked to a supplier record, so the whole network is "
            "shown. Set your email as the supplier contact to scope this view."
        )


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def _overview() -> None:
    name = st.session_state.get("user_name", "there")
    first = str(name).split()[0] if name else "there"
    first = first.capitalize() if first.islower() else first
    supplier = _linked_supplier()
    pos = _scoped_pos(supplier)
    shipments = data.shipments()
    exceptions = data.exceptions()

    head, action = st.columns([3, 1.1])
    with head:
        page_header(
            f"Good day, {first}",
            "Orders waiting on you, and how your deliveries are tracking.",
            eyebrow="Supplier workspace",
            bordered=False,
        )
    with action:
        spacer(1.6)
        if st.button("Add product", type="primary", width="stretch"):
            goto(ROLE, "products", product_action="add")
        if st.button("Refresh data", width="stretch"):
            data.invalidate()
            st.rerun()
    divider()
    _scope_note(supplier)

    awaiting = [p for p in pos if p.get("status") == "ISSUED"]
    confirmed = [p for p in pos if p.get("status") == "CONFIRMED"]
    delayed_pos = [p for p in pos if p.get("status") == "DELAYED"]
    delayed_ships = [s for s in shipments if s.get("status") in ("DELAYED", "EXCEPTION")]
    active_exc = data.active_exceptions(exceptions)
    committed = sum(float(p.get("total_cost") or 0) for p in pos)

    kpi_row(
        [
            {
                "label": "To confirm",
                "value": len(awaiting),
                "meta": "Waiting on you",
                "tone": "critical" if awaiting else "good",
            },
            {"label": "Confirmed", "value": len(confirmed), "tone": "good"},
            {
                "label": "Late orders",
                "value": len(delayed_pos),
                "tone": "warning" if delayed_pos else None,
            },
            {
                "label": "Late shipments",
                "value": len(delayed_ships),
                "tone": "warning" if delayed_ships else None,
            },
            {
                "label": "Exceptions",
                "value": len(active_exc),
                "meta": "Shared record",
                "tone": "accent" if active_exc else None,
            },
            {
                "label": "Order value",
                "value": format_currency(committed, compact=True),
                "meta": f"{len(pos)} orders",
            },
        ]
    )

    # Quick navigation — the main destinations, one click from the overview.
    nav_exc, nav_po, nav_ship, _ = st.columns([1, 1, 1, 1.3])
    with nav_exc:
        if st.button(f"Open exceptions · {len(active_exc)}", key="dash_exceptions", width="stretch"):
            goto(ROLE, "exceptions")
    with nav_po:
        if st.button(
            f"Confirm orders · {len(awaiting)}",
            key="dash_confirm",
            width="stretch",
            type="primary" if awaiting else "secondary",
        ):
            goto(ROLE, "purchase_orders")
    with nav_ship:
        if st.button("Track shipments", key="dash_shipments", width="stretch"):
            goto(ROLE, "shipments")

    if awaiting:
        callout(
            "Orders need a commitment",
            f"<b>{len(awaiting)}</b> purchase order{'s' if len(awaiting) > 1 else ''} "
            "issued to you have not been confirmed. Confirming publishes your commitment "
            "to the buyer's exception agent.",
            tone="accent",
        )

    section("Incoming purchase orders", f"{len(pos)} records")
    if not pos:
        empty_state("No purchase orders", "Orders issued to you will appear here.")
    else:
        st.markdown(_po_table(pos[:8]), unsafe_allow_html=True)
        open_col, _rest = st.columns([1, 3])
        with open_col:
            if st.button("Open purchase orders", width="stretch"):
                goto(ROLE, "purchase_orders")

    left, right = st.columns(2)
    with left:
        section("Order state mix", "Your purchase orders")
        with card_container("po_state_mix"):
            if pos:
                st.plotly_chart(
                    charts.state_bars(charts.counts_of(pos, "status")),
                    width="stretch",
                    config={"displayModeBar": False},
                )
            else:
                empty_state("Nothing to chart", icon="○")
    with right:
        section("Shipment status", "Movements on the shared record")
        with card_container("ship_state_mix"):
            if shipments:
                st.plotly_chart(
                    charts.state_bars(charts.counts_of(shipments, "status")),
                    width="stretch",
                    config={"displayModeBar": False},
                )
            else:
                empty_state("Nothing to chart", icon="○")


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------

def _po_table(rows: List[Dict[str, Any]]) -> str:
    return data_table(
        [
            Col(
                "PO",
                render=lambda r: (
                    f'<span>{r.get("po_number")}</span>'
                    f'<span class="sub">Issued {format_date(r.get("issue_date"))}</span>'
                ),
                strong=True,
                nowrap=True,
            ),
            Col(
                "Destination",
                render=lambda r: (
                    f'<span>{str(r.get("warehouse_name") or "—")[:24]}</span>'
                    f'<span class="sub">{str(r.get("warehouse_city") or "")}</span>'
                ),
            ),
            Col("Status", render=lambda r: badge(r.get("status")), nowrap=True),
            Col("Units", render=lambda r: format_number(r.get("units_ordered")), align="num"),
            Col("Value", render=lambda r: format_currency(r.get("total_cost")), align="num"),
            Col("Due", render=lambda r: format_date(r.get("expected_delivery_date")), nowrap=True),
            Col(
                "Expedited",
                render=lambda r: badge("Yes", tone="serious")
                if r.get("is_expedited")
                else badge("No", tone="neutral"),
            ),
        ],
        rows,
    )


def _purchase_orders() -> None:
    page_header(
        "Purchase orders",
        "Confirm what you can deliver. Your commitment is what the buyer's agent "
        "reasons over when a disruption happens.",
        eyebrow="Orders",
    )
    confirmed = st.session_state.pop("po_confirmed", None)
    if confirmed:
        callout(
            "Order confirmed",
            "Your commitment is now visible to the buyer and to the exception agent.",
            tone="good",
        )

    supplier = _linked_supplier()
    _scope_note(supplier)
    rows = _scoped_pos(supplier)
    if not rows:
        empty_state("No purchase orders", "Orders issued to you will appear here.")
        return

    kpi_row(
        [
            {"label": "Orders", "value": len(rows)},
            {
                "label": "Awaiting confirmation",
                "value": len([p for p in rows if p.get("status") == "ISSUED"]),
                "tone": "critical",
            },
            {
                "label": "In transit",
                "value": len([p for p in rows if p.get("status") == "IN_TRANSIT"]),
                "tone": "accent",
            },
            {
                "label": "Received",
                "value": len([p for p in rows if p.get("status") == "RECEIVED"]),
                "tone": "good",
            },
            {
                "label": "Value",
                "value": format_currency(
                    sum(float(p.get("total_cost") or 0) for p in rows), compact=True
                ),
            },
        ],
        per_row=5,
    )

    pool = list_controls(
        rows,
        key="sup_pos",
        search_fields=("po_number", "warehouse_name", "warehouse_city"),
        placeholder="Search PO or destination",
        views={
            "Open": [p for p in rows if p.get("status") in OPEN_PO_STATES],
            "Awaiting confirmation": [p for p in rows if p.get("status") == "ISSUED"],
            "Received": [p for p in rows if p.get("status") == "RECEIVED"],
            "All": rows,
        },
        default_view="Open",
        filters=(("Destination", "warehouse_name", "All destinations"),),
        sorts=(
            ("Due soonest", "expected_delivery_date", False),
            ("Due latest", "expected_delivery_date", True),
            ("Value: high to low", "total_cost", True),
            ("Units: high to low", "units_ordered", True),
        ),
    )

    section("Orders", _shown(pool))
    if not pool:
        empty_state("Nothing matches", "Try another view or search term.", icon="○")
        return
    st.markdown(_po_table(pool[:TABLE_LIMIT]), unsafe_allow_html=True)
    _truncation_note(pool)

    section("Respond to an order", "Confirm the commitment or review the lines")
    labels = {
        f"{po.get('po_number')} · {title_case(po.get('status'))} · {format_currency(po.get('total_cost'))} · "
        f"due {format_date(po.get('expected_delivery_date'))}": po
        for po in pool[:TABLE_LIMIT]
    }
    po = labels[st.selectbox("Order", list(labels), key="sup_po_detail", label_visibility="collapsed")]
    st.markdown(
        '<div class="card"><div class="card-body">'
        + detail_grid(
            [
                ("Status", badge(po.get("status"))),
                ("Destination", po.get("warehouse_name")),
                ("Destination city", po.get("warehouse_city")),
                ("Issued", format_date(po.get("issue_date"))),
                ("Required by", format_date(po.get("expected_delivery_date"))),
                ("Units", format_number(po.get("units_ordered"))),
                ("Order value", format_currency(po.get("total_cost"))),
                (
                    "Expedited",
                    badge("Yes", tone="serious") if po.get("is_expedited") else badge("No", tone="neutral"),
                ),
            ]
        )
        + "</div></div>",
        unsafe_allow_html=True,
    )
    lines = data.purchase_order_lines(po["id"])
    if lines:
        st.markdown(
            data_table(
                [
                    Col("Product", key="product_name", strong=True),
                    Col("SKU", render=lambda r: mono(r.get("sku"))),
                    Col("Ordered", render=lambda r: format_number(r.get("quantity_ordered")), align="num"),
                    Col("Received", render=lambda r: format_number(r.get("quantity_received")), align="num"),
                    Col("Unit cost", render=lambda r: format_currency(r.get("unit_cost")), align="num"),
                    Col("Line total", render=lambda r: format_currency(r.get("total_cost")), align="num"),
                ],
                lines,
            ),
            unsafe_allow_html=True,
        )
    if po.get("notes"):
        st.caption(po.get("notes"))
    if po.get("status") == "ISSUED":
        confirm, _ = st.columns([1, 3])
        with confirm:
            if st.button("Confirm order", key=f"confirm_{po['id']}", type="primary", width="stretch"):
                _confirm_po(po["id"])


def _confirm_po(po_id: str) -> None:
    try:
        get_db().execute_statement(
            "UPDATE purchase_orders SET status='CONFIRMED', updated_at=CURRENT_TIMESTAMP "
            "WHERE id=:id",
            {"id": po_id},
        )
    except Exception as err:
        st.error(f"Could not confirm the order: {err}")
        return
    data.invalidate()
    st.session_state["po_confirmed"] = po_id
    st.rerun()


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------

def _shipments() -> None:
    page_header(
        "Shipments",
        "Movements against your orders, with schedule variance as the buyer sees it.",
        eyebrow="Logistics",
    )
    rows = data.shipments()
    if not rows:
        empty_state("No shipments recorded")
        return

    active = [s for s in rows if s.get("status") in ACTIVE_SHIPMENT_STATES]
    delayed = [s for s in active if s.get("status") in ("DELAYED", "EXCEPTION")]
    delivered = [s for s in rows if s.get("status") == "DELIVERED"]
    late = [s for s in delivered if float(s.get("delay_hours") or 0) > 0]
    on_time = (1 - len(late) / len(delivered)) * 100 if delivered else 100.0
    typical_late = sum(float(s.get("delay_hours") or 0) for s in late) / len(late) / 24 if late else 0.0
    kpi_row(
        [
            {"label": "In flight", "value": len(active), "meta": f"{len(rows):,} on record"},
            {"label": "Delayed", "value": len(delayed), "tone": "critical" if delayed else "good"},
            {
                "label": "On-time delivery",
                "value": format_percent(on_time, 1),
                "meta": f"{len(delivered):,} delivered",
                "tone": "good" if on_time >= 90 else "warning",
            },
            {"label": "Typical lateness", "value": f"{typical_late:.0f} days", "meta": "Average of late deliveries"},
        ],
        per_row=4,
    )

    pool = list_controls(
        rows,
        key="sup_ships",
        search_fields=("shipment_number", "po_number", "origin_location", "destination_location"),
        placeholder="Search shipment, PO or place",
        views={"In flight": active, "Delayed": delayed, "Delivered": delivered, "All": rows},
        default_view="In flight",
        filters=(
            ("Carrier", "carrier_name", "All carriers"),
            ("Destination", "destination_location", "All destinations"),
        ),
        sorts=(
            ("Due soonest", "expected_delivery_date", False),
            ("Due latest", "expected_delivery_date", True),
            ("Most late first", "delay_hours", True),
        ),
    )

    section("Movements", _shown(pool))
    if not pool:
        empty_state("Nothing matches", "Try another view or search term.", icon="○")
        return
    st.markdown(
        data_table(
            [
                Col(
                    "Shipment",
                    render=lambda r: (
                        f'<span>{r.get("shipment_number") or str(r.get("id"))[:12]}</span>'
                        f'<span class="sub">{r.get("po_number") or "Direct"}</span>'
                    ),
                    strong=True,
                    nowrap=True,
                ),
                Col(
                    "Destination",
                    render=lambda r: (
                        f'<span>{str(r.get("destination_location") or "—")[:34]}</span>'
                        f'<span class="sub">from {str(r.get("origin_location") or "—")[:28]}</span>'
                    ),
                ),
                Col(
                    "Carrier",
                    render=lambda r: (
                        f'<span>{str(r.get("carrier_name") or r.get("carrier_id") or "—")[:28]}</span>'
                        f'<span class="sub">{title_case(r.get("carrier_mode") or "")}</span>'
                    ),
                ),
                Col("Status", render=lambda r: badge(r.get("status")), nowrap=True),
                Col("ETA", render=lambda r: format_date(r.get("expected_delivery_date")), nowrap=True),
                Col("Schedule", render=lambda r: delay_label(r.get("delay_hours")), nowrap=True),
            ],
            pool[:TABLE_LIMIT],
        ),
        unsafe_allow_html=True,
    )
    _truncation_note(pool)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def _products() -> None:
    if st.session_state.get("product_action") == "add":
        _add_product()
        return

    head, action = st.columns([3, 1])
    with head:
        page_header(
            "Product catalogue",
            "What buyers can order from the network, with the pricing the agent costs "
            "resolutions against.",
            eyebrow="Catalogue",
            bordered=False,
        )
    with action:
        spacer(1.6)
        if st.button("Add product", type="primary", width="stretch"):
            st.session_state["product_action"] = "add"
            st.rerun()
    divider()

    saved = st.session_state.pop("product_saved", None)
    if saved:
        callout("Product added", f"<b>{saved}</b> is now orderable by buyers.", tone="good")

    rows = data.products()
    if not rows:
        empty_state("No products yet", "Add your first product to make it orderable.")
        return

    margins = []
    for product in rows:
        try:
            price = float(product.get("unit_price") or 0)
            cost = float(product.get("unit_cost") or 0)
            if price and price != cost:
                margins.append((price - cost) / price)
        except (TypeError, ValueError):
            continue
    kpi_row(
        [
            {"label": "Products", "value": len(rows)},
            {
                "label": "Critical items",
                "value": len([p for p in rows if p.get("critical_level") in ("HIGH", "CRITICAL")]),
                "tone": "warning",
            },
            {
                "label": "Average margin",
                "value": format_percent(sum(margins) / len(margins) * 100, 1) if margins else "—",
                "meta": f"{len(margins):,} priced above cost",
            },
            {"label": "Categories", "value": len({p.get("category") for p in rows if p.get("category")})},
        ],
        per_row=4,
    )

    def margin_cell(record: Dict[str, Any]) -> str:
        try:
            price = float(record.get("unit_price") or 0)
            cost = float(record.get("unit_cost") or 0)
        except (TypeError, ValueError):
            return "—"
        if not price or price == cost:
            return "—"
        fraction = (price - cost) / price
        tone = "good" if fraction >= 0.25 else ("warn" if fraction >= 0.1 else "bad")
        return f'<span>{fraction * 100:.0f}%</span>' + meter(fraction, tone)

    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    catalogue = [dict(p, criticality_rank=rank.get(p.get("critical_level"), -1)) for p in rows]
    pool = list_controls(
        catalogue,
        key="sup_products",
        search_fields=("name", "sku", "category"),
        placeholder="Search name, SKU or category",
        views={
            "All": catalogue,
            "Critical or high": [p for p in catalogue if p.get("critical_level") in ("HIGH", "CRITICAL")],
        },
        default_view="All",
        filters=(
            ("Category", "category", "All categories"),
            ("Criticality", "critical_level", "Any criticality"),
        ),
        sorts=(
            ("Name A-Z", "name", False),
            ("Unit price: high to low", "unit_price", True),
            ("Unit price: low to high", "unit_price", False),
            ("Unit cost: high to low", "unit_cost", True),
            ("Most critical first", "criticality_rank", True),
        ),
    )

    section("Catalogue", _shown(pool))
    st.markdown(
        data_table(
            [
                Col(
                    "Product",
                    render=lambda r: (
                        f'<span>{r.get("name")}</span>'
                        f'<span class="sub">{r.get("category") or "Uncategorised"}</span>'
                    ),
                    strong=True,
                ),
                Col("SKU", render=lambda r: mono(r.get("sku"))),
                Col("Criticality", render=lambda r: badge(r.get("critical_level"))),
                Col("Unit price", render=lambda r: format_currency(r.get("unit_price")), align="num"),
                Col("Unit cost", render=lambda r: format_currency(r.get("unit_cost")), align="num"),
                Col("Margin", render=margin_cell),
                Col(
                    "Weight",
                    render=lambda r: f'{float(r.get("weight_kg")):.3f} kg' if r.get("weight_kg") else "—",
                    align="num",
                ),
            ],
            pool[:TABLE_LIMIT],
        ),
        unsafe_allow_html=True,
    )
    _truncation_note(pool)


def _add_product() -> None:
    head, action = st.columns([3, 1])
    with head:
        page_header(
            "Add product",
            "New products become orderable immediately and are costed into resolutions.",
            eyebrow="Catalogue",
            bordered=False,
        )
    with action:
        spacer(1.6)
        if st.button("Cancel", width="stretch"):
            st.session_state["product_action"] = "list"
            st.rerun()
    divider()

    with st.form("add_product"):
        left, right = st.columns(2)
        with left:
            name = st.text_input("Product name *", placeholder="Electronic control module")
            sku = st.text_input("SKU *", placeholder="ECM-001")
            category = st.text_input("Category", placeholder="Electronics")
            critical = st.selectbox("Criticality", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], index=1)
        with right:
            price = st.number_input("Unit price (USD) *", min_value=0.01, value=10.0, step=1.0)
            cost = st.number_input("Unit cost (USD) *", min_value=0.01, value=7.5, step=1.0)
            weight = st.number_input("Weight (kg)", min_value=0.01, value=1.0, step=0.1)
        submitted = st.form_submit_button("Save product", type="primary", width="stretch")

    if not submitted:
        return

    errors = []
    if not name.strip():
        errors.append("Product name is required.")
    if not sku.strip():
        errors.append("SKU is required.")
    if cost > price:
        errors.append("Unit cost is higher than unit price — check the figures.")
    if errors:
        for message in errors:
            st.error(message)
        return

    _save_product(name.strip(), sku.strip().upper(), category.strip(), price, cost, weight, critical)


def _save_product(
    name: str, sku: str, category: str, price: float, cost: float, weight: float, critical: str
) -> None:
    try:
        db = get_db()
        if db.execute_query("SELECT id FROM products WHERE sku = :sku", {"sku": sku}):
            st.error(f"A product with SKU {sku} already exists.")
            return
        db.execute_statement(
            "INSERT INTO products (id, sku, name, category, unit_price, unit_cost, weight_kg, "
            "critical_level, created_at, updated_at) "
            "VALUES (:id, :sku, :name, :cat, :unit_price, :unit_cost, :weight_kg, "
            ":critical_level, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            {
                "id": f"PROD-{uuid.uuid4().hex[:8].upper()}",
                "sku": sku,
                "name": name,
                "cat": category or None,
                "unit_price": price,
                "unit_cost": cost,
                "weight_kg": weight,
                "critical_level": critical,
            },
        )
    except Exception as err:
        st.error(f"Could not save the product: {err}")
        return

    data.invalidate()
    st.session_state["product_action"] = "list"
    st.session_state["product_saved"] = name
    st.rerun()


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

def _performance() -> None:
    page_header(
        "Performance",
        "Delivery reliability measured on the same records the buyer sees.",
        eyebrow="Insights",
    )
    supplier = _linked_supplier()
    _scope_note(supplier)

    pos = _scoped_pos(supplier)
    shipments = data.shipments()
    if not pos and not shipments:
        empty_state("Nothing to measure yet")
        return

    delayed_pos = [p for p in pos if p.get("status") == "DELAYED"]
    received = [p for p in pos if p.get("status") == "RECEIVED"]
    delayed_ships = [s for s in shipments if s.get("status") in ("DELAYED", "EXCEPTION")]
    delivered = [s for s in shipments if s.get("status") == "DELIVERED"]
    on_time = (1 - len(delayed_pos) / len(pos)) * 100 if pos else 100.0
    avg_delay = (
        sum(float(s.get("delay_hours") or 0) for s in shipments) / len(shipments)
        if shipments
        else 0
    )

    kpi_row(
        [
            {
                "label": "On-time orders",
                "value": format_percent(on_time, 1),
                "meta": f"{len(delayed_pos)} of {len(pos)} delayed",
                "tone": "good" if on_time >= 90 else "warning",
            },
            {"label": "Orders completed", "value": len(received), "tone": "good"},
            {
                "label": "Delayed shipments",
                "value": len(delayed_ships),
                "tone": "critical" if delayed_ships else "good",
            },
            {"label": "Shipments delivered", "value": len(delivered)},
            {
                "label": "Average delay",
                "value": f"{avg_delay:,.1f} h",
                "meta": "Per shipment",
                "tone": "warning" if avg_delay else None,
            },
        ],
        per_row=5,
    )

    if supplier:
        left, right = st.columns(2)
        with left:
            reliability = float(supplier.get("reliability_rating") or 0)
            capacity = int(supplier.get("capacity_units_per_day") or 0)
            used = int(supplier.get("current_capacity_utilized") or 0)
            utilisation = (used / capacity) if capacity else 0
            st.markdown(
                '<div class="card"><div class="card-head">'
                '<div class="card-title">Your supplier record</div></div><div class="card-body">'
                + detail_grid(
                    [
                        ("Reliability rating", format_percent(reliability * 100, 1)),
                        ("Risk band", badge("LOW" if reliability >= 0.95 else "MEDIUM" if reliability >= 0.85 else "HIGH")),
                        ("Standard lead time", f"{supplier.get('lead_time_days', '—')} days"),
                        ("Expedite lead time", f"{supplier.get('expedite_lead_time_days', '—')} days"),
                        (
                            "Expedite multiplier",
                            f"×{float(supplier.get('expedite_cost_multiplier')):.2f}"
                            if supplier.get("expedite_cost_multiplier") is not None else "Not recorded",
                        ),
                        ("Daily capacity", f"{capacity:,} units"),
                    ]
                )
                + '<div style="margin-top:1rem"><div class="detail-label">Capacity utilisation</div>'
                f'<div class="detail-value">{utilisation * 100:.0f}% · {max(0, capacity - used):,} units free</div>'
                + meter(utilisation, "bad" if utilisation > 0.9 else "warn" if utilisation > 0.7 else "good")
                + "</div></div></div>",
                unsafe_allow_html=True,
            )
        with right:
            section("Order states")
            with card_container("po_states_scoped"):
                st.plotly_chart(
                    charts.state_bars(charts.counts_of(pos, "status")),
                    width="stretch",
                    config={"displayModeBar": False},
                )
    else:
        left, right = st.columns(2)
        with left:
            section("Order states", "Across the network")
            with card_container("po_states_all"):
                st.plotly_chart(
                    charts.state_bars(charts.counts_of(pos, "status")),
                    width="stretch",
                    config={"displayModeBar": False},
                )
        with right:
            section("Shipment states", "Movements on the shared record")
            with card_container("ship_states_all"):
                st.plotly_chart(
                    charts.state_bars(charts.counts_of(shipments, "status")),
                    width="stretch",
                    config={"displayModeBar": False},
                )

    section("Order history", f"{min(len(pos), 100):,} most recent of {len(pos):,}")
    st.markdown(
        data_table(
            [
                Col("PO", key="po_number", strong=True),
                Col("Status", render=lambda r: badge(r.get("status"))),
                Col("Value", render=lambda r: format_currency(r.get("total_cost")), align="num"),
                Col("Promised", render=lambda r: format_date(r.get("expected_delivery_date"))),
                Col("Delivered", render=lambda r: format_date(r.get("actual_delivery_date"))),
                Col(
                    "Expedited",
                    render=lambda r: badge("Yes", tone="serious")
                    if r.get("is_expedited")
                    else badge("No", tone="neutral"),
                ),
            ],
            pos[:100],
        ),
        unsafe_allow_html=True,
    )
