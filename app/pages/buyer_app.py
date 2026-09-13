"""
Buyer workspace: overview, exception queue, approvals, and the operational
records the agent reasons over (shipments, purchase orders, inventory, suppliers)
plus the governance audit trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import streamlit as st

from app import charts, data
from app.pages.audit import render_audit_page
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
    inventory_state,
    kpi_row,
    legend,
    list_controls,
    meter,
    mono,
    page_header,
    risk_from_reliability,
    section,
    spacer,
    title_case,
)
from database.client import get_db

ROLE = "BUYER"

TABLE_LIMIT = 150  # rows rendered per table; search narrows the rest
ACTIVE_SHIPMENT_STATES = ("CREATED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELAYED", "REROUTED", "EXCEPTION")
OPEN_PO_STATES = ("ISSUED", "CONFIRMED", "IN_TRANSIT", "DELAYED", "EXPEDITED")


def _shown(pool: List[Dict[str, Any]]) -> str:
    return f"{min(len(pool), TABLE_LIMIT):,} of {len(pool):,} shown"


def _truncation_note(pool: List[Dict[str, Any]]) -> None:
    if len(pool) > TABLE_LIMIT:
        st.caption(f"Showing the first {TABLE_LIMIT}. Search to narrow the list.")


def render_buyer_app() -> None:
    page = render_sidebar(ROLE)
    render_account_bar(ROLE, page)
    if page == "dashboard":
        _overview()
    elif page == "exceptions":
        render_exceptions_page(ROLE)
    elif page == "approvals":
        _approvals()
    elif page == "shipments":
        _shipments()
    elif page == "purchase_orders":
        _purchase_orders()
    elif page == "inventory":
        _inventory()
    elif page == "products":
        _products()
    elif page == "suppliers":
        _suppliers()
    elif page == "audit":
        render_audit_page()
    elif page == "profile":
        render_profile_page(ROLE)


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def _overview() -> None:
    name = st.session_state.get("user_name", "there")
    first = str(name).split()[0] if name else "there"
    first = first.capitalize() if first.islower() else first

    shipments = data.shipments()
    pos = data.purchase_orders()
    inventory = data.inventory()
    exceptions = data.exceptions()

    active_exc = data.active_exceptions(exceptions)
    pending = data.pending_approvals(exceptions)
    low = data.low_stock(inventory)
    delayed = [s for s in shipments if s.get("status") in ("DELAYED", "EXCEPTION")]
    in_flight = [
        s for s in shipments
        if s.get("status") in ("CREATED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELAYED", "REROUTED")
    ]
    open_pos = [p for p in pos if p.get("status") in ("ISSUED", "CONFIRMED", "IN_TRANSIT", "EXPEDITED")]
    exposure = sum(float(e.get("estimated_financial_loss") or 0) for e in active_exc)

    head, actions = st.columns([3, 1.15])
    with head:
        page_header(
            f"Good day, {first}",
            "Everything the agent is watching across procurement, logistics and inventory.",
            eyebrow="Buyer workspace",
            bordered=False,
        )
    with actions:
        spacer(1.6)
        if st.button("Raise purchase order", type="primary", width="stretch"):
            goto(ROLE, "purchase_orders", po_action="create")
        if st.button("Refresh data", width="stretch"):
            data.invalidate()
            st.rerun()
    divider()
    _provenance()

    kpi_row(
        [
            {"label": "In flight", "value": len(in_flight), "meta": "Shipments moving"},
            {
                "label": "Delayed",
                "value": len(delayed),
                "meta": "Behind plan",
                "tone": "critical" if delayed else None,
            },
            {"label": "Open POs", "value": len(open_pos), "meta": f"of {len(pos)} total"},
            {
                "label": "Stock at risk",
                "value": len(low),
                "meta": "At or below reorder point",
                "tone": "warning" if low else None,
            },
            {
                "label": "Exceptions",
                "value": len(active_exc),
                "meta": f"Active · {format_currency(exposure, compact=True)}",
                "tone": "accent" if active_exc else None,
            },
            {
                "label": "Awaiting you",
                "value": len(pending),
                "meta": "Approval decisions",
                "tone": "critical" if pending else "good",
            },
        ]
    )

    # Quick navigation — the main destinations, one click from the overview.
    nav_exc, nav_appr, nav_ship, _ = st.columns([1, 1, 1, 1.3])
    with nav_exc:
        if st.button(f"Open exceptions · {len(active_exc)}", key="dash_exceptions", width="stretch"):
            goto(ROLE, "exceptions")
    with nav_appr:
        if st.button(
            f"Review approvals · {len(pending)}",
            key="dash_approvals",
            width="stretch",
            type="primary" if pending else "secondary",
        ):
            goto(ROLE, "approvals")
    with nav_ship:
        if st.button("Track shipments", key="dash_shipments", width="stretch"):
            goto(ROLE, "shipments")

    if pending:
        callout(
            "Approval required",
            f"<b>{len(pending)}</b> resolution plan{'s' if len(pending) > 1 else ''} "
            "cannot execute until a human decides. Open <b>Approvals</b> to review the "
            "recommended option, its cost and its risk.",
            tone="accent",
        )

    left, right = st.columns([1.55, 1])

    with left:
        section("Exception queue", "Highest severity first")
        if not active_exc:
            empty_state(
                "No active exceptions",
                "Detected disruptions will appear here with their investigation state.",
                icon="✓",
            )
        else:
            order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            ranked = sorted(active_exc, key=lambda e: order.get(e.get("severity"), 9))
            st.markdown(
                data_table(
                    [
                        Col(
                            "Exception",
                            render=lambda r: (
                                f'<span>{str(r.get("title") or "")[:52]}</span>'
                                f'<span class="sub">{r.get("exception_code")} · '
                                f'{title_case(r.get("category"))}</span>'
                            ),
                            strong=True,
                        ),
                        Col(
                            "Severity / state",
                            render=lambda r: (
                                badge(r.get("severity"))
                                + '<span class="sub" style="margin-top:.35rem">'
                                + badge(r.get("status"))
                                + "</span>"
                            ),
                            nowrap=True,
                        ),
                        Col(
                            "Exposure",
                            render=lambda r: format_currency(
                                r.get("estimated_financial_loss"), compact=True
                            ),
                            align="num",
                            nowrap=True,
                        ),
                    ],
                    ranked[:6],
                ),
                unsafe_allow_html=True,
            )
            if st.button("Open exception workspace", width="stretch"):
                goto(ROLE, "exceptions")

    with right:
        section("Where exceptions come from")
        with card_container("exc_by_category"):
            if exceptions:
                st.plotly_chart(
                    charts.magnitude_bars(charts.counts_of(exceptions, "category")),
                    width="stretch",
                    config={"displayModeBar": False},
                )
            else:
                empty_state("Nothing detected yet", icon="○")
        section("Financial exposure")
        with card_container("exc_exposure"):
            if active_exc:
                st.plotly_chart(
                    charts.exposure_bars(active_exc),
                    width="stretch",
                    config={"displayModeBar": False},
                )
            else:
                empty_state("No open exposure", icon="○")

    section("Shipments in flight", f"{len(in_flight):,} of {len(shipments):,} on record")
    if in_flight:
        st.markdown(_shipment_table(in_flight[:8]), unsafe_allow_html=True)
    else:
        empty_state("Nothing in flight", icon="○")

    if low:
        section("Stock lines at or below reorder point", f"{len(low)} lines")
        st.markdown(_inventory_table(low[:6]), unsafe_allow_html=True)


def _provenance() -> None:
    sources = data.data_sources()
    if sources:
        names = " · ".join(f"{src['name']} (as of {str(src.get('source_as_of'))[:10]})" for src in sources)
        st.caption(f"Operational data: {names} — public Kaggle datasets, replayed to today.")


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

def _approvals() -> None:
    page_header(
        "Approvals",
        "Resolution plans are held here until a person approves a specific option. "
        "Nothing is written to the operational record before that decision.",
        eyebrow="Human decision gate",
    )

    pending = data.pending_approvals()
    if not pending:
        empty_state(
            "Nothing waiting on you",
            "Every investigated exception has been approved, rejected or resolved.",
            icon="✓",
        )
        return

    total_cost = 0.0
    for exc in pending:
        option = data.recommended_option(exc["id"])
        total_cost += float((option or {}).get("estimated_cost") or 0)

    kpi_row(
        [
            {"label": "Decisions pending", "value": len(pending), "tone": "critical"},
            {
                "label": "Recommended spend",
                "value": format_currency(total_cost, compact=True),
                "meta": "If every recommendation is approved",
            },
            {
                "label": "Exposure held",
                "value": format_currency(
                    sum(float(e.get("estimated_financial_loss") or 0) for e in pending),
                    compact=True,
                ),
                "meta": "Loss avoided by resolving",
                "tone": "accent",
            },
        ],
        per_row=3,
    )

    spacer(0.5)
    for exc in pending:
        option = data.recommended_option(exc["id"]) or {}
        with card_container(f"approval_{exc['id']}"):
            st.markdown(
                f'<div class="card-title" style="font-size:.98rem">{exc.get("title")}</div>'
                f'<div class="section-note" style="margin:.3rem 0 .9rem">'
                f'{mono(exc.get("exception_code"))} &nbsp; {badge(exc.get("severity"))} &nbsp; '
                f'{badge(exc.get("category"), tone="neutral")}</div>'
                + detail_grid(
                    [
                        (
                            "Recommended action",
                            option.get("option_name") or "Awaiting agent plan",
                        ),
                        ("Action type", mono(option.get("action_type"))),
                        ("Resolution cost", format_currency(option.get("estimated_cost"))),
                        (
                            "Time to effect",
                            f'{float(option.get("expected_time_hours") or 0):.0f} hrs'
                            if option.get("expected_time_hours") is not None
                            else "—",
                        ),
                        ("Operational risk", badge(option.get("operational_risk"))),
                        (
                            "Agent confidence",
                            format_percent(
                                float(option.get("confidence_score") or 0) * 100
                            ),
                        ),
                        (
                            "Exception exposure",
                            format_currency(exc.get("estimated_financial_loss")),
                        ),
                    ]
                ),
                unsafe_allow_html=True,
            )
            if option.get("reasoning"):
                st.markdown(
                    f'<div class="callout accent" style="margin-top:.9rem">'
                    f'<div class="callout-title">Why this option</div>'
                    f'<div class="callout-body">{option.get("reasoning")}</div></div>',
                    unsafe_allow_html=True,
                )
            if st.button(
                "Review evidence and decide",
                key=f"approve_{exc['id']}",
                type="primary",
            ):
                goto(ROLE, "exceptions", exception_focus=exc["id"])


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------

def _shipment_table(rows: List[Dict[str, Any]]) -> str:
    return data_table(
        [
            Col(
                "Shipment",
                render=lambda r: (
                    f'<span>{r.get("shipment_number") or str(r.get("id"))[:12]}</span>'
                    f'<span class="sub">{str(r.get("po_number") or "Direct")}</span>'
                ),
                strong=True,
                nowrap=True,
            ),
            Col(
                "Lane",
                render=lambda r: (
                    f'<span>{str(r.get("origin_location") or "—")[:26]} → '
                    f'{str(r.get("destination_location") or "—")[:26]}</span>'
                    f'<span class="sub">{str(r.get("current_location") or "Location not reported")[:40]}</span>'
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
            Col(
                "Freight",
                render=lambda r: format_currency(r.get("shipping_cost")),
                align="num",
            ),
        ],
        rows,
    )


def _shipments() -> None:
    page_header(
        "Shipments",
        "Inbound and outbound movements with carrier, lane and schedule variance.",
        eyebrow="Logistics",
    )
    rows = data.shipments()
    if not rows:
        empty_state("No shipments recorded", "Shipments created against purchase orders appear here.")
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
        key="buyer_ships",
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
            ("Freight: high to low", "shipping_cost", True),
        ),
    )

    section("Movements", _shown(pool))
    if pool:
        st.markdown(_shipment_table(pool[:TABLE_LIMIT]), unsafe_allow_html=True)
        _truncation_note(pool)
    else:
        empty_state("Nothing matches", "Try another view or search term.", icon="○")

    left, right = st.columns([1.55, 1])
    with right:
        section("Status mix", "Shipments in flight")
        with card_container("ship_status"):
            st.plotly_chart(
                charts.state_bars(charts.counts_of(active or rows, "status")),
                width="stretch",
                config={"displayModeBar": False},
            )
    with left:
        section("Behind plan", "Candidates for exception investigation")
        if not delayed:
            empty_state("Everything on schedule", "No shipment is behind plan.", icon="✓")
        for ship in delayed[:25]:
            label = (
                f"{ship.get('shipment_number')} · "
                f"{float(ship.get('delay_hours') or 0) / 24:.0f} days late · "
                f"{str(ship.get('destination_location') or '')[:30]}"
            )
            with st.expander(label):
                st.markdown(
                    detail_grid(
                        [
                            ("Carrier", ship.get("carrier_name") or ship.get("carrier_id")),
                            ("Mode", title_case(ship.get("carrier_mode"))),
                            ("Origin", ship.get("origin_location")),
                            ("Destination", ship.get("destination_location")),
                            ("Current location", ship.get("current_location") or "Not reported"),
                            ("Expected", format_date(ship.get("expected_delivery_date"))),
                            ("Freight cost", format_currency(ship.get("shipping_cost"))),
                            ("Linked PO", mono(ship.get("po_number"))),
                        ]
                    ),
                    unsafe_allow_html=True,
                )
                if ship.get("tracking_notes"):
                    st.markdown(
                        f'<div class="callout danger" style="margin-top:.9rem">'
                        f'<div class="callout-title">Tracking notes</div>'
                        f'<div class="callout-body">{ship.get("tracking_notes")}</div></div>',
                        unsafe_allow_html=True,
                    )


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------

def _purchase_orders() -> None:
    if st.session_state.get("po_action") == "create":
        _create_purchase_order()
        return

    head, action = st.columns([3, 1])
    with head:
        page_header(
            "Purchase orders",
            "Commitments to suppliers, their promised dates and current state.",
            eyebrow="Procurement",
            bordered=False,
        )
    with action:
        spacer(1.6)
        if st.button("New purchase order", type="primary", width="stretch"):
            st.session_state["po_action"] = "create"
            st.rerun()
    divider()

    created = st.session_state.pop("po_created", None)
    if created:
        callout(
            "Purchase order created",
            f"<b>{created}</b> was issued to the supplier and is now awaiting confirmation.",
            tone="good",
        )

    rows = data.purchase_orders()
    if not rows:
        empty_state(
            "No purchase orders yet",
            "Raise one to request product from a supplier into a warehouse.",
        )
        return

    open_pos = [p for p in rows if p.get("status") in OPEN_PO_STATES]
    delayed = [p for p in open_pos if p.get("status") == "DELAYED"]
    kpi_row(
        [
            {"label": "Open POs", "value": len(open_pos), "meta": f"{len(rows):,} on record"},
            {"label": "Delayed", "value": len(delayed), "tone": "critical" if delayed else "good"},
            {
                "label": "Awaiting confirmation",
                "value": len([p for p in open_pos if p.get("status") == "ISSUED"]),
                "tone": "warning",
            },
            {
                "label": "Open value",
                "value": format_currency(sum(float(p.get("total_cost") or 0) for p in open_pos), compact=True),
                "meta": "Committed, not yet received",
            },
        ],
        per_row=4,
    )

    pool = list_controls(
        rows,
        key="buyer_pos",
        search_fields=("po_number", "supplier_name", "warehouse_name", "warehouse_city"),
        placeholder="Search PO, supplier or destination",
        views={
            "Open": open_pos,
            "Delayed": delayed,
            "Received": [p for p in rows if p.get("status") == "RECEIVED"],
            "All": rows,
        },
        default_view="Open",
        filters=(
            ("Supplier", "supplier_name", "All suppliers"),
            ("Destination", "warehouse_name", "All destinations"),
        ),
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

    section("Order detail", "Line items as recorded in the database")
    labels = {
        f"{po.get('po_number')} · {str(po.get('supplier_name') or '')[:32]} · {format_currency(po.get('total_cost'))}": po
        for po in pool[:TABLE_LIMIT]
    }
    po = labels[st.selectbox("Purchase order", list(labels), key="po_detail", label_visibility="collapsed")]
    _po_detail(po)


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
                "Supplier",
                render=lambda r: (
                    f'<span>{str(r.get("supplier_name") or r.get("supplier_id") or "—")[:30]}</span>'
                    f'<span class="sub">{str(r.get("supplier_city") or "")[:30]}</span>'
                ),
            ),
            Col(
                "Destination",
                render=lambda r: (
                    f'<span>{str(r.get("warehouse_name") or "—")[:30]}</span>'
                    f'<span class="sub">{str(r.get("warehouse_city") or "")}</span>'
                ),
            ),
            Col("Status", render=lambda r: badge(r.get("status")), nowrap=True),
            Col("Units", render=lambda r: format_number(r.get("units_ordered")), align="num"),
            Col("Value", render=lambda r: format_currency(r.get("total_cost")), align="num"),
            Col("Due", render=lambda r: format_date(r.get("expected_delivery_date")), nowrap=True),
            Col(
                "Expedited",
                render=lambda r: badge("Yes", tone="serious") if r.get("is_expedited")
                else badge("No", tone="neutral"),
            ),
        ],
        rows,
    )


def _po_detail(po: Dict[str, Any]) -> None:
    st.markdown(
        '<div class="card"><div class="card-body">'
        + detail_grid(
            [
                ("Status", badge(po.get("status"))),
                ("Supplier", po.get("supplier_name") or po.get("supplier_id")),
                ("Supplier code", mono(po.get("supplier_code"))),
                ("Destination", po.get("warehouse_name")),
                ("Issued", format_date(po.get("issue_date"))),
                ("Expected", format_date(po.get("expected_delivery_date"))),
                ("Actual delivery", format_date(po.get("actual_delivery_date"))),
                ("Total cost", format_currency(po.get("total_cost"))),
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


def _create_purchase_order() -> None:
    head, action = st.columns([3, 1])
    with head:
        page_header(
            "New purchase order",
            "Request product from a supplier into one of your warehouses. "
            "This writes a live purchase order and its line item.",
            eyebrow="Procurement",
            bordered=False,
        )
    with action:
        spacer(1.6)
        if st.button("Cancel", width="stretch"):
            st.session_state["po_action"] = "list"
            st.rerun()
    divider()

    suppliers = data.suppliers()
    products = data.products()
    warehouses = data.warehouses()

    missing = [
        label
        for label, rows in (("suppliers", suppliers), ("products", products), ("warehouses", warehouses))
        if not rows
    ]
    if missing:
        st.error(f"Cannot raise an order: no {', '.join(missing)} in the database.")
        return

    form, summary = st.columns([1.5, 1])

    with form:
        with card_container("po_form"):
            supplier_labels = {
                f"{s['name']} · {s['code']}": s for s in suppliers
            }
            supplier = supplier_labels[
                st.selectbox("Supplier", list(supplier_labels.keys()), key="po_supplier")
            ]
            st.markdown(
                detail_grid(
                    [
                        (
                            "Reliability",
                            format_percent(float(supplier.get("reliability_rating") or 0) * 100),
                        ),
                        ("Standard lead time", f"{supplier.get('lead_time_days', '—')} days"),
                        ("Expedite lead time", f"{supplier.get('expedite_lead_time_days', '—')} days"),
                        ("Location", _location(supplier)),
                    ]
                ),
                unsafe_allow_html=True,
            )

            catalogue = [p for p in products if p.get("primary_supplier_id") == supplier["id"]]
            if catalogue:
                st.caption(f"{len(catalogue):,} products this supplier usually supplies.")
            product_labels = {f"{p['name']} · {p['sku']}": p for p in (catalogue or products)}
            product = product_labels[
                st.selectbox("Product", list(product_labels.keys()), key="po_product")
            ]

            quantity = st.number_input(
                "Quantity (units)", min_value=1, max_value=100000, value=100, step=10, key="po_qty"
            )

            warehouse_labels = {f"{w['name']} · {w['city']}": w for w in warehouses}
            warehouse = warehouse_labels[
                st.selectbox(
                    "Destination warehouse", list(warehouse_labels.keys()), key="po_warehouse"
                )
            ]

            lead_days = int(supplier.get("lead_time_days") or 7)
            delivery = st.date_input(
                "Required delivery date",
                value=datetime.now().date() + timedelta(days=lead_days),
                min_value=datetime.now().date() + timedelta(days=1),
                key="po_date",
            )
            notes = st.text_area(
                "Notes for the supplier", placeholder="Packaging, tolerances, dock times…",
                height=90, key="po_notes",
            )

    unit_price = float(product.get("unit_cost") or product.get("unit_price") or 0)  # purchased at cost
    total = unit_price * int(quantity)
    lead_ok = (delivery - datetime.now().date()).days >= lead_days

    with summary:
        section("Order summary")
        st.markdown(
            '<div class="card"><div class="card-body">'
            + detail_grid(
                [
                    ("Supplier", supplier.get("name")),
                    ("Product", product.get("name")),
                    ("SKU", mono(product.get("sku"))),
                    ("Quantity", f"{int(quantity):,} units"),
                    ("Unit cost", format_currency(unit_price)),
                    ("Destination", warehouse.get("name")),
                    ("Required by", str(delivery)),
                    ("Criticality", badge(product.get("critical_level"))),
                ]
            )
            + f'<div style="margin-top:1rem;padding-top:.9rem;border-top:1px solid var(--line)">'
            f'<div class="kpi-label">Estimated total</div>'
            f'<div class="kpi-value">{format_currency(total)}</div></div>'
            "</div></div>",
            unsafe_allow_html=True,
        )
        if not lead_ok:
            callout(
                "Tighter than the supplier's lead time",
                f"{supplier.get('name')} quotes <b>{lead_days} days</b> as standard. "
                "This date may need expediting, which the agent can cost as a resolution option.",
                tone="accent",
            )
        if st.button("Create purchase order", type="primary", width="stretch"):
            _submit_purchase_order(supplier, product, warehouse, int(quantity), unit_price, delivery, notes)


def _submit_purchase_order(
    supplier: Dict[str, Any],
    product: Dict[str, Any],
    warehouse: Dict[str, Any],
    quantity: int,
    unit_price: float,
    delivery,
    notes: str,
) -> None:
    try:
        db = get_db()
        po_id = f"PO-{uuid.uuid4().hex[:8].upper()}"
        po_number = f"PO-{datetime.now().strftime('%Y')}-{uuid.uuid4().hex[:4].upper()}"
        total_cost = quantity * unit_price
        db.execute_statement(
            "INSERT INTO purchase_orders (id, po_number, supplier_id, destination_warehouse_id, "
            "expected_delivery_date, status, total_cost, notes, created_at, updated_at) "
            "VALUES (:id, :po_number, :supplier_id, :wh_id, :exp_date, 'ISSUED', "
            ":total_cost, :notes, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            {
                "id": po_id,
                "po_number": po_number,
                "supplier_id": supplier["id"],
                "wh_id": warehouse["id"],
                "exp_date": str(delivery),
                "total_cost": total_cost,
                "notes": notes or "Buyer request via RELAY",
            },
        )
        db.execute_statement(
            "INSERT INTO purchase_order_items (id, purchase_order_id, product_id, "
            "quantity_ordered, quantity_received, unit_cost, total_cost, created_at) "
            "VALUES (:id, :po_id, :prod_id, :qty, 0, :unit_cost, :total_cost, CURRENT_TIMESTAMP)",
            {
                "id": f"POI-{uuid.uuid4().hex[:8].upper()}",
                "po_id": po_id,
                "prod_id": product["id"],
                "qty": quantity,
                "unit_cost": unit_price,
                "total_cost": total_cost,
            },
        )
    except Exception as err:
        st.error(f"Could not create the purchase order: {err}")
        return

    data.invalidate()
    st.session_state["po_action"] = "list"
    st.session_state["po_created"] = po_number
    st.rerun()


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def _inventory_table(rows: List[Dict[str, Any]]) -> str:
    def cover(record: Dict[str, Any]) -> str:
        try:
            available = float(record.get("quantity_available") or 0)
            reorder = float(record.get("reorder_point") or 0) or 1
        except (TypeError, ValueError):
            return "—"
        fraction = available / (reorder * 1.5)
        state = inventory_state(
            record.get("quantity_available"),
            record.get("reorder_point"),
            record.get("safety_stock"),
        )
        tone = {"CRITICAL": "bad", "LOW": "warn", "HEALTHY": "good"}[state]
        return meter(fraction, tone)

    return data_table(
        [
            Col(
                "Product",
                render=lambda r: (
                    f'<span>{str(r.get("product_name") or "")[:34]}</span>'
                    f'<span class="sub">{r.get("sku")}</span>'
                ),
                strong=True,
            ),
            Col(
                "Warehouse",
                render=lambda r: (
                    f'<span>{str(r.get("warehouse_name") or "")[:24]}</span>'
                    f'<span class="sub">{r.get("warehouse_city")}</span>'
                ),
            ),
            Col(
                "State",
                render=lambda r: badge(
                    inventory_state(
                        r.get("quantity_available"), r.get("reorder_point"), r.get("safety_stock")
                    )
                ),
            ),
            Col("Cover", render=cover),
            Col(
                "Available",
                render=lambda r: format_number(r.get("quantity_available")),
                align="num",
            ),
            Col("Reserved", render=lambda r: format_number(r.get("quantity_reserved")), align="num"),
            Col(
                "In transit",
                render=lambda r: format_number(r.get("quantity_in_transit")),
                align="num",
            ),
            Col("Reorder at", render=lambda r: format_number(r.get("reorder_point")), align="num"),
            Col("Safety", render=lambda r: format_number(r.get("safety_stock")), align="num"),
        ],
        rows,
    )


def _inventory() -> None:
    page_header(
        "Inventory",
        "Stock positions across every warehouse, measured against reorder point and safety stock.",
        eyebrow="Inventory",
    )
    rows = data.inventory()
    if not rows:
        empty_state("No inventory records", "Stock lines appear once warehouses hold product.")
        return

    states = [
        inventory_state(r.get("quantity_available"), r.get("reorder_point"), r.get("safety_stock"))
        for r in rows
    ]
    units = sum(float(r.get("quantity_available") or 0) for r in rows)
    stock_value = sum(
        float(r.get("quantity_available") or 0) * float(r.get("unit_cost") or 0) for r in rows
    )
    kpi_row(
        [
            {"label": "Stock lines", "value": len(rows), "meta": f"{format_number(units)} units"},
            {
                "label": "Below safety stock",
                "value": states.count("CRITICAL"),
                "tone": "critical" if states.count("CRITICAL") else "good",
            },
            {
                "label": "Below reorder point",
                "value": states.count("LOW"),
                "tone": "warning" if states.count("LOW") else None,
            },
            {"label": "Healthy", "value": states.count("HEALTHY"), "tone": "good"},
            {
                "label": "Stock value",
                "value": format_currency(stock_value, compact=True),
                "meta": "Available units at cost",
            },
        ],
        per_row=5,
    )

    left, right = st.columns([1.8, 1])
    with left:
        section("Lowest positions", "Available units against reorder point")
        with card_container("stock_position"):
            st.plotly_chart(
                charts.stock_position(rows),
                width="stretch",
                config={"displayModeBar": False},
            )
            legend(
                [
                    ("Below safety stock", charts.STATUS_CRITICAL),
                    ("Below reorder point", charts.STATUS_WARNING),
                    ("Healthy", charts.STATUS_GOOD),
                    ("Reorder point", "#0B1220"),
                ]
            )
    with right:
        section("Criticality mix", "Product criticality of stocked lines")
        with card_container("stock_criticality"):
            st.plotly_chart(
                charts.magnitude_bars(charts.counts_of(rows, "critical_level")),
                width="stretch",
                config={"displayModeBar": False},
            )

    pool = list_controls(
        rows,
        key="buyer_inv",
        search_fields=("product_name", "sku"),
        placeholder="Search product or SKU",
        views={
            "Needs attention": [r for r, state in zip(rows, states) if state != "HEALTHY"],
            "Below safety stock": [r for r, state in zip(rows, states) if state == "CRITICAL"],
            "All": rows,
        },
        default_view="Needs attention",
        filters=(
            ("Warehouse", "warehouse_name", "All warehouses"),
            ("Category", "category", "All categories"),
            ("Criticality", "critical_level", "Any criticality"),
        ),
        sorts=(
            ("Available: low to high", "quantity_available", False),
            ("Available: high to low", "quantity_available", True),
            ("Product A-Z", "product_name", False),
            ("Reorder point: high to low", "reorder_point", True),
        ),
    )

    section("Stock lines", _shown(pool))
    if pool:
        st.markdown(_inventory_table(pool[:TABLE_LIMIT]), unsafe_allow_html=True)
        _truncation_note(pool)
    else:
        empty_state("Nothing matches", "Try another view, warehouse or search term.", icon="○")


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def _lead_time_note(record: Dict[str, Any]) -> str:
    days = record.get("lead_time_days")
    return f"{int(days)} day lead time" if days else "Lead time not recorded"


def _shortage_badge(record: Dict[str, Any]) -> str:
    lines = int(record.get("short_lines") or 0)
    return badge(f"{lines} line(s)", tone="critical") if lines else badge("None", tone="good")


def _products() -> None:
    page_header(
        "Products",
        "Everything the network can order, who usually supplies it, and how much stock is on hand.",
        eyebrow="Catalogue",
    )
    rows = data.product_catalogue()
    if not rows:
        empty_state("No products on record", "Products appear here once the catalogue is loaded.")
        return

    short = [r for r in rows if int(r.get("short_lines") or 0) > 0]
    critical = [r for r in rows if r.get("critical_level") in ("HIGH", "CRITICAL")]
    unstocked = [r for r in rows if int(r.get("warehouse_count") or 0) == 0]
    kpi_row(
        [
            {"label": "Products", "value": f"{len(rows):,}"},
            {
                "label": "Critical or high",
                "value": f"{len(critical):,}",
                "meta": "By product criticality",
                "tone": "warning" if critical else None,
            },
            {
                "label": "With a shortage",
                "value": f"{len(short):,}",
                "meta": "At or below safety stock",
                "tone": "critical" if short else "good",
            },
            {"label": "Not stocked", "value": f"{len(unstocked):,}", "meta": "No warehouse holds them"},
            {"label": "Categories", "value": len({r.get("category") for r in rows if r.get("category")})},
        ],
        per_row=5,
    )

    pool = list_controls(
        rows,
        key="buyer_products",
        search_fields=("name", "sku", "supplier_name", "category"),
        placeholder="Search product, SKU or supplier",
        views={
            "All": rows,
            "With a shortage": short,
            "Critical or high": critical,
            "Not stocked": unstocked,
        },
        default_view="All",
        filters=(
            ("Category", "category", "All categories"),
            ("Criticality", "critical_level", "Any criticality"),
            ("Supplier", "supplier_name", "All suppliers"),
        ),
        sorts=(
            ("Name A-Z", "name", False),
            ("Stock: low to high", "stock_available", False),
            ("Stock: high to low", "stock_available", True),
            ("Unit cost: high to low", "unit_cost", True),
            ("Unit cost: low to high", "unit_cost", False),
            ("Most critical first", "criticality_rank", True),
        ),
    )

    section("Catalogue", _shown(pool))
    if not pool:
        empty_state("Nothing matches", "Try another view, filter or search term.", icon="○")
        return

    st.markdown(
        data_table(
            [
                Col(
                    "Product",
                    render=lambda r: (
                        f'<span>{str(r.get("name") or "")[:46]}</span>'
                        f'<span class="sub">{r.get("category") or "Uncategorised"}</span>'
                    ),
                    strong=True,
                ),
                Col("SKU", render=lambda r: mono(r.get("sku")), nowrap=True),
                Col("Criticality", render=lambda r: badge(r.get("critical_level")), nowrap=True),
                Col(
                    "Usual supplier",
                    render=lambda r: (
                        f'<span>{str(r.get("supplier_name") or "Not recorded")[:28]}</span>'
                        f'<span class="sub">{_lead_time_note(r)}</span>'
                    ),
                ),
                Col("Unit cost", render=lambda r: format_currency(r.get("unit_cost")), align="num"),
                Col(
                    "Stock on hand",
                    render=lambda r: (
                        f'<span>{format_number(r.get("stock_available"))}</span>'
                        f'<span class="sub">{int(r.get("warehouse_count") or 0)} warehouse(s)</span>'
                    ),
                    align="num",
                ),
                Col("Shortage", render=_shortage_badge, nowrap=True),
            ],
            pool[:TABLE_LIMIT],
        ),
        unsafe_allow_html=True,
    )
    _truncation_note(pool)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

def _location(record: Dict[str, Any]) -> str:
    parts = [p for p in (record.get("city"), record.get("country")) if p and p != "Not recorded"]
    return ", ".join(dict.fromkeys(parts)) or "Not recorded"


def _suppliers() -> None:
    page_header(
        "Suppliers",
        "Reliability, lead time and remaining daily capacity — the inputs behind "
        "expedite and supplier-switch resolutions.",
        eyebrow="Procurement",
    )
    rows = [
        dict(
            supplier,
            risk=risk_from_reliability(supplier.get("reliability_rating")),
            spare_capacity=max(
                0,
                int(supplier.get("capacity_units_per_day") or 0)
                - int(supplier.get("current_capacity_utilized") or 0),
            ),
        )
        for supplier in data.suppliers()
    ]
    if not rows:
        empty_state("No suppliers on record")
        return

    pos = data.purchase_orders()
    po_by_supplier: Dict[str, int] = {}
    for po in pos:
        if po.get("status") not in OPEN_PO_STATES:
            continue
        key = po.get("supplier_id")
        po_by_supplier[key] = po_by_supplier.get(key, 0) + 1

    risks = [risk_from_reliability(s.get("reliability_rating")) for s in rows]
    avg_reliability = sum(float(s.get("reliability_rating") or 0) for s in rows) / len(rows)
    kpi_row(
        [
            {"label": "Suppliers", "value": len(rows)},
            {
                "label": "Average reliability",
                "value": format_percent(avg_reliability * 100, 1),
                "tone": "good" if avg_reliability >= 0.9 else "warning",
            },
            {
                "label": "Elevated risk",
                "value": risks.count("HIGH") + risks.count("MEDIUM"),
                "meta": "Reliability below 95%",
                "tone": "warning",
            },
            {
                "label": "Spare capacity",
                "value": format_number(
                    sum(
                        max(
                            0,
                            int(s.get("capacity_units_per_day") or 0)
                            - int(s.get("current_capacity_utilized") or 0),
                        )
                        for s in rows
                    )
                ),
                "meta": "Units per day",
            },
        ],
        per_row=4,
    )

    def capacity_cell(record: Dict[str, Any]) -> str:
        total = int(record.get("capacity_units_per_day") or 0)
        used = int(record.get("current_capacity_utilized") or 0)
        free = max(0, total - used)
        utilisation = (used / total) if total else 0
        tone = "bad" if utilisation > 0.9 else ("warn" if utilisation > 0.7 else "good")
        return (
            f'<span>{free:,} free of {total:,}</span>'
            f'<span class="sub">{utilisation * 100:.0f}% utilised</span>'
            + meter(utilisation, tone)
        )

    pool = list_controls(
        rows,
        key="buyer_suppliers",
        search_fields=("name", "code", "category", "city", "country"),
        placeholder="Search supplier, code or category",
        filters=(
            ("Category", "category", "All categories"),
            ("Risk", "risk", "Any risk"),
            ("Country", "country", "All countries"),
        ),
        sorts=(
            ("Reliability: high to low", "reliability_rating", True),
            ("Reliability: low to high", "reliability_rating", False),
            ("Lead time: shortest", "lead_time_days", False),
            ("Spare capacity: high to low", "spare_capacity", True),
            ("Name A-Z", "name", False),
        ),
    )

    section("Supplier base", _shown(pool))
    if not pool:
        empty_state("Nothing matches", "Try another filter or search term.", icon="○")
        return
    st.markdown(
        data_table(
            [
                Col(
                    "Supplier",
                    render=lambda r: (
                        f'<span>{r.get("name")}</span>'
                        f'<span class="sub">{r.get("code")} · {r.get("category") or "—"}</span>'
                    ),
                    strong=True,
                ),
                Col(
                    "Location",
                    render=_location,
                ),
                Col(
                    "Reliability",
                    render=lambda r: (
                        f'<span>{float(r.get("reliability_rating") or 0) * 100:.0f}%</span>'
                        + meter(
                            float(r.get("reliability_rating") or 0),
                            "good"
                            if float(r.get("reliability_rating") or 0) >= 0.95
                            else ("warn" if float(r.get("reliability_rating") or 0) >= 0.85 else "bad"),
                        )
                    ),
                ),
                Col("Risk", render=lambda r: badge(r.get("risk")), nowrap=True),
                Col("Daily capacity", render=capacity_cell),
                Col(
                    "Lead time",
                    render=lambda r: (
                        f'<span>{r.get("lead_time_days", "—")} days</span>'
                        f'<span class="sub">{r.get("expedite_lead_time_days", "—")} expedited</span>'
                    ),
                ),
                Col(
                    "Expedite cost",
                    render=lambda r: (
                        f'×{float(r.get("expedite_cost_multiplier")):.2f}'
                        if r.get("expedite_cost_multiplier") is not None else "—"
                    ),
                    align="num",
                ),
                Col(
                    "Open POs",
                    render=lambda r: str(po_by_supplier.get(r.get("id"), 0)),
                    align="num",
                ),
            ],
            pool[:TABLE_LIMIT],
        ),
        unsafe_allow_html=True,
    )
