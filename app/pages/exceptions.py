"""
Exception workspace — the operator-facing view of the agent lifecycle:

    perceive → investigate → reason → recommend → approve → act → verify

Every stage reads live from the database so the page reflects what the agent has
actually persisted, and execution stays behind the human approval gate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from app import data
from app.ui import (
    Col,
    badge,
    callout,
    data_table,
    detail_grid,
    empty_state,
    format_currency,
    format_datetime,
    format_percent,
    kpi_row,
    mono,
    page_header,
    section,
    spacer,
    stages,
    title_case,
)
from database.queries.exceptions import ExceptionQueries
from services.investigation_service import InvestigationService
from services.resolution_service import ResolutionService

LIFECYCLE = [
    "Perceive",
    "Investigate",
    "Reason",
    "Recommend",
    "Approve",
    "Act",
    "Verify",
]

_STATUS_STAGE = {
    "OPEN": "Perceive",
    "INVESTIGATING": "Investigate",
    "PENDING_APPROVAL": "Approve",
    "APPROVED": "Act",
    "RESOLVED": "Verify",
    "REJECTED": "Approve",
    "IGNORED": "Perceive",
}


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a pydantic model or a database row."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        value = obj.get(name, default)
    else:
        value = getattr(obj, name, default)
    return getattr(value, "value", value)  # unwrap Enum


def _show_failure(summary: str, err: Exception) -> None:
    """Explain a failed agent step in plain language; keep the raw error out of sight."""
    st.error(summary)
    with st.expander("Technical details"):
        st.code(f"{type(err).__name__}: {err}", language="text")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def render_exceptions_page(role: str = "BUYER") -> None:
    can_decide = role.upper() == "BUYER"

    page_header(
        "Exception workspace",
        "The agent investigates across procurement, logistics and inventory, then "
        "argues for one resolution. Execution waits for a human decision.",
        eyebrow="Agent lifecycle",
    )

    try:
        exceptions = ExceptionQueries.list_exceptions()
    except Exception as err:
        st.error(f"Could not load exceptions: {err}")
        return

    if not exceptions:
        empty_state(
            "No exceptions on record",
            "Detected disruptions appear here for investigation.",
            icon="○",
        )
        return

    active = [e for e in exceptions if e.get("status") not in ("RESOLVED", "REJECTED", "IGNORED")]
    kpi_row(
        [
            {"label": "Total", "value": len(exceptions)},
            {"label": "Active", "value": len(active), "tone": "accent" if active else None},
            {
                "label": "Awaiting approval",
                "value": len([e for e in exceptions if e.get("status") == "PENDING_APPROVAL"]),
                "tone": "critical",
            },
            {
                "label": "Resolved",
                "value": len([e for e in exceptions if e.get("status") == "RESOLVED"]),
                "tone": "good",
            },
            {
                "label": "Open exposure",
                "value": format_currency(
                    sum(float(e.get("estimated_financial_loss") or 0) for e in active),
                    compact=True,
                ),
            },
        ],
        per_row=5,
    )

    labels: Dict[str, str] = {}
    for exc in exceptions:
        severity = str(exc.get("severity") or "")
        label = (
            f"{exc.get('exception_code')}  ·  {str(exc.get('title') or '')[:62]}  "
            f"·  {severity} · {str(exc.get('status') or '').replace('_', ' ')}"
        )
        labels[label] = exc["id"]

    focus = st.session_state.pop("exception_focus", None)
    index = 0
    if focus:
        for position, exception_id in enumerate(labels.values()):
            if exception_id == focus:
                index = position
                break

    section("Select an exception")
    selected_label = st.selectbox(
        "Exception", list(labels.keys()), index=index, label_visibility="collapsed"
    )
    selected_id = labels[selected_label]

    exc = ExceptionQueries.get_exception(selected_id)
    if not exc:
        st.error("That exception could not be retrieved.")
        return

    stages(LIFECYCLE, _STATUS_STAGE.get(exc.get("status"), "Perceive"))
    _overview_card(exc)

    inv_key = f"inv_{selected_id}"
    res_key = f"res_{selected_id}"
    exec_key = f"exec_{selected_id}"

    exc = _investigation_stage(exc, selected_id, inv_key)
    options, recommendation, meta = _resolution_stage(exc, selected_id, inv_key, res_key)
    if options:
        exc = _approval_stage(exc, selected_id, options, recommendation, meta, exec_key, can_decide)
        _verification_stage(exc, selected_id, exec_key)
    _trace_stage(exc)


# ---------------------------------------------------------------------------
# Stage 0 — perceived exception
# ---------------------------------------------------------------------------

def _overview_card(exc: Dict[str, Any]) -> None:
    st.markdown(
        '<div class="card"><div class="card-head">'
        f'<div class="card-title">{exc.get("title")}</div>'
        f'<div>{badge(exc.get("severity"))} &nbsp; {badge(exc.get("status"))}</div>'
        '</div><div class="card-body">'
        f'<div class="callout-body" style="margin-bottom:.4rem">{exc.get("description")}</div>'
        + detail_grid(
            [
                ("Exception code", mono(exc.get("exception_code"))),
                ("Category", title_case(exc.get("category"))),
                ("Type", title_case(exc.get("exception_type"))),
                ("Detected", format_datetime(exc.get("detected_at"))),
                ("Financial exposure", format_currency(exc.get("estimated_financial_loss"))),
                ("Order", mono(exc.get("order_id"))),
                ("Shipment", mono(exc.get("shipment_id"))),
                ("Purchase order", mono(exc.get("purchase_order_id"))),
                ("Warehouse", mono(exc.get("warehouse_id"))),
                ("Product", mono(exc.get("product_id"))),
            ]
        )
        + "</div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Stage 1/2 — investigation and reasoning
# ---------------------------------------------------------------------------

def _investigation_stage(exc: Dict[str, Any], exception_id: str, inv_key: str) -> Dict[str, Any]:
    section("1 · Cross-functional investigation", "The agent chooses which records matter")

    finalized = exc.get("status") in ("RESOLVED", "REJECTED")
    run, status = st.columns([1, 3])
    with run:
        clicked = st.button(
            "Run investigation",
            type="primary",
            width="stretch",
            disabled=finalized,
            help="This exception is finalized; re-investigating would reopen a closed case." if finalized else None,
        )
    if clicked:
        with st.spinner("Reading shipments, orders, inventory, suppliers and capacity…"):
            try:
                st.session_state[inv_key] = InvestigationService.investigate(exception_id)
                data.invalidate()
                exc = ExceptionQueries.get_exception(exception_id) or exc
            except Exception as err:
                _show_failure("The investigation could not finish. Please try again.", err)
    with status:
        if st.session_state.get(inv_key):
            st.caption("Investigation complete — findings persisted to the exception record.")

    result = st.session_state.get(inv_key)

    if result is not None:
        tools = _field(result, "tools_used", []) or []
        if tools:
            chips = "".join(
                f'<span class="tool-chip">✓ {str(t).replace("_", " ").title()}</span>' for t in tools
            )
            st.markdown(
                f'<div class="section-note" style="margin-bottom:.4rem">'
                f"{len(tools)} tools selected by the agent</div>"
                f'<div class="chip-list">{chips}</div>',
                unsafe_allow_html=True,
            )

        steps = _field(result, "investigation_steps", []) or []
        if steps:
            with st.expander(f"Execution trace · {len(steps)} steps"):
                blocks = []
                for step in steps:
                    blocks.append(
                        '<div class="trace-step">'
                        f'<div class="trace-head">Step {_field(step, "step_number")}'
                        f'{mono(_field(step, "tool_name"))}</div>'
                        f'<div class="trace-thought">{_field(step, "thought", "")}</div>'
                        f'<div class="trace-out">{_field(step, "tool_output_summary", "")}</div>'
                        "</div>"
                    )
                st.markdown(f'<div class="trace">{"".join(blocks)}</div>', unsafe_allow_html=True)

        evidence = _field(result, "evidence", []) or []
        left, right = st.columns(2)
        with left:
            callout("Root cause", str(_field(result, "root_cause", "—")), tone="accent")
            if evidence:
                items = "".join(f"<li>{item}</li>" for item in evidence[:6])
                callout("Evidence gathered", f'<ul style="margin:0;padding-left:1.1rem">{items}</ul>')
        with right:
            callout(
                "Cross-functional impact",
                f'<b>Stockout risk:</b> {_field(result, "stockout_risk", "—")}<br/>'
                f'<b>Inventory:</b> {_field(result, "inventory_impact", "—")}<br/>'
                f'<b>Procurement:</b> {_field(result, "procurement_impact", "—")}<br/>'
                f'<b>Logistics:</b> {_field(result, "logistics_impact", "—")}<br/>'
                f'<b>Customer:</b> {_field(result, "customer_impact", "—")}',
            )
    elif exc.get("root_cause"):
        left, right = st.columns(2)
        with left:
            callout("Root cause (persisted)", str(exc.get("root_cause")), tone="accent")
        with right:
            callout("Business impact (persisted)", str(exc.get("business_impact") or "—"))
    else:
        callout(
            "Not investigated yet",
            "Run the investigation to let the agent gather evidence across procurement, "
            "logistics and inventory before any resolution is proposed.",
        )
    return exc


# ---------------------------------------------------------------------------
# Stage 3/4 — resolution options
# ---------------------------------------------------------------------------

def _resolution_stage(
    exc: Dict[str, Any], exception_id: str, inv_key: str, res_key: str
):
    section("2 · Resolution options", "Scored on cost, time to effect and operational risk")

    investigated = bool(st.session_state.get(inv_key)) or bool(exc.get("root_cause"))
    finalized = exc.get("status") in ("RESOLVED", "REJECTED")
    run, status = st.columns([1, 3])
    with run:
        clicked = st.button(
            "Generate resolutions",
            type="primary" if investigated and not finalized else "secondary",
            width="stretch",
            disabled=not investigated or finalized,
            help=(
                "This exception is finalized; regenerating would reopen a closed case."
                if finalized
                else (None if investigated else "Run the investigation first")
            ),
        )
    if clicked:
        with st.spinner("Costing alternatives against supplier capacity, carriers and stock…"):
            try:
                payload = st.session_state.get(inv_key) or exception_id
                st.session_state[res_key] = ResolutionService.plan_resolution(payload)
                data.invalidate()
                exc = ExceptionQueries.get_exception(exception_id) or exc
            except Exception as err:
                _show_failure("Resolutions could not be generated for this exception. Please try again.", err)
    with status:
        if st.session_state.get(res_key):
            st.caption("Options generated and stored against the exception.")

    result = st.session_state.get(res_key)
    options: List[Any] = []
    recommendation: Optional[Any] = None
    meta = {"reasoning": "", "confidence": 0.85, "approval_required": True}

    if result is not None:
        recommendation = _field(result, "recommended_option")
        options = [recommendation] + list(_field(result, "alternatives", []) or [])
        meta = {
            "reasoning": _field(result, "reasoning", ""),
            "confidence": float(_field(result, "confidence", 0.85) or 0.85),
            "approval_required": bool(_field(result, "approval_required", True)),
        }
    else:
        stored = exc.get("resolution_options") or []
        if stored:
            options = list(stored)
            recommendation = next((o for o in options if o.get("is_recommended")), options[0])
            meta = {
                "reasoning": recommendation.get("reasoning", ""),
                "confidence": float(recommendation.get("confidence_score") or 0.85),
                "approval_required": exc.get("status") not in ("RESOLVED", "REJECTED"),
            }

    if not options:
        callout(
            "No resolution plan yet",
            "Generate resolutions to see the feasible options side by side before deciding.",
        )
        return [], None, meta

    confidence_badge = badge(
        "{:.0f}% confidence".format(meta["confidence"] * 100), tone="info", dot=False
    )
    status = exc.get("status")
    if status == "RESOLVED":
        gate_badge = badge("Approved & executed", tone="good")
    elif status == "REJECTED":
        gate_badge = badge("Rejected", tone="critical")
    elif meta["approval_required"]:
        gate_badge = badge("Approval required", tone="serious")
    else:
        gate_badge = badge("No approval needed", tone="good")
    st.markdown(
        '<div class="card"><div class="card-head">'
        '<div class="card-title">★ Recommended resolution</div>'
        f"<div>{confidence_badge} &nbsp; {gate_badge}</div>"
        '</div><div class="card-body">'
        f'<div style="font-size:1.02rem;font-weight:600;color:var(--ink-900);letter-spacing:-.02em">'
        f'{_field(recommendation, "option_name")} {mono(_field(recommendation, "action_type"))}</div>'
        f'<div class="callout-body" style="margin:.5rem 0 .9rem">'
        f'{_field(recommendation, "description", "")}</div>'
        + detail_grid(
            [
                ("Estimated cost", format_currency(_field(recommendation, "estimated_cost"))),
                (
                    "Time to effect",
                    f'{float(_field(recommendation, "expected_time_hours", 0) or 0):.0f} hrs',
                ),
                ("Operational risk", badge(_field(recommendation, "operational_risk"))),
                (
                    "Feasible",
                    badge("Yes", tone="good")
                    if _field(recommendation, "feasibility", True)
                    else badge("No", tone="critical"),
                ),
                ("Option id", mono(_field(recommendation, "id"))),
            ]
        )
        + (
            f'<div class="callout accent" style="margin-top:.9rem">'
            f'<div class="callout-title">Agent reasoning</div>'
            f'<div class="callout-body">{meta["reasoning"]}</div></div>'
            if meta["reasoning"]
            else ""
        )
        + "</div></div>",
        unsafe_allow_html=True,
    )

    rows = [
        {
            "recommended": bool(_field(o, "is_recommended", False)),
            "name": _field(o, "option_name"),
            "action": _field(o, "action_type"),
            "cost": _field(o, "estimated_cost"),
            "hours": _field(o, "expected_time_hours"),
            "risk": _field(o, "operational_risk"),
            "feasible": _field(o, "feasibility", True),
            "inventory": _field(o, "inventory_impact"),
            "customer": _field(o, "customer_impact"),
        }
        for o in options
    ]
    section("Options compared", f"{len(rows)} candidate plans")
    st.markdown(
        data_table(
            [
                Col(
                    "Option",
                    render=lambda r: (
                        f'<span>{"★ " if r["recommended"] else ""}{r["name"]}</span>'
                        f'<span class="sub">{r["action"]}</span>'
                    ),
                    strong=True,
                ),
                Col("Cost", render=lambda r: format_currency(r["cost"]), align="num"),
                Col(
                    "Hours",
                    render=lambda r: f'{float(r["hours"] or 0):.0f}',
                    align="num",
                ),
                Col("Risk", render=lambda r: badge(r["risk"])),
                Col(
                    "Feasible",
                    render=lambda r: badge("Yes", tone="good")
                    if r["feasible"]
                    else badge("No", tone="critical"),
                ),
                Col("Inventory impact", render=lambda r: str(r["inventory"] or "—")[:70]),
                Col("Customer impact", render=lambda r: str(r["customer"] or "—")[:70]),
            ],
            rows,
        ),
        unsafe_allow_html=True,
    )
    return options, recommendation, meta


# ---------------------------------------------------------------------------
# Stage 5 — human approval gate
# ---------------------------------------------------------------------------

def _approval_stage(
    exc: Dict[str, Any],
    exception_id: str,
    options: List[Any],
    recommendation: Any,
    meta: Dict[str, Any],
    exec_key: str,
    can_decide: bool,
) -> Dict[str, Any]:
    section("3 · Human approval gate", "No database change happens before this decision")

    status = exc.get("status")
    if status == "RESOLVED":
        callout(
            "Approved and executed",
            "This exception was approved and the resolution has been applied to the "
            "operational record. The verified change is shown below.",
            tone="good",
        )
        return exc
    if status == "REJECTED":
        callout(
            "Rejected by an operator",
            "Execution was blocked. No supply-chain record was altered.",
            tone="danger",
        )
        return exc

    if not can_decide:
        callout(
            "Buyer decision pending",
            "Approval sits with the buyer organisation. You can review the evidence and "
            "the costed options here, but execution is gated to the buyer's decision.",
            tone="accent",
        )
        return exc

    choices: Dict[str, Any] = {}
    for option in options:
        star = "★ " if _field(option, "is_recommended", False) else ""
        label = (
            f'{star}{_field(option, "option_name")} · '
            f'{format_currency(_field(option, "estimated_cost"))} · '
            f'{_field(option, "operational_risk")} risk'
        )
        choices[label] = _field(option, "id")

    callout(
        "Decision required",
        f'<b>Recommended:</b> {_field(recommendation, "option_name")} '
        f'({_field(recommendation, "action_type")})<br/>'
        f'<b>Cost:</b> {format_currency(_field(recommendation, "estimated_cost"))} &nbsp;·&nbsp; '
        f'<b>Risk:</b> {_field(recommendation, "operational_risk")} &nbsp;·&nbsp; '
        f'<b>Confidence:</b> {format_percent(meta["confidence"] * 100)}<br/>'
        "Approving executes the action against the live database and records the audit trail.",
        tone="accent",
    )

    picked_label = st.selectbox("Option to act on", list(choices.keys()), index=0)
    option_id = choices[picked_label]

    approve, reject, _ = st.columns([1.2, 1, 2])
    with approve:
        approved = st.button("Approve & execute", type="primary", width="stretch")
    with reject:
        rejected = st.button("Reject", width="stretch")

    if approved:
        with st.spinner("Executing the approved action and verifying the database state…"):
            try:
                st.session_state[exec_key] = ResolutionService.approve_resolution(
                    exception_id=exception_id,
                    resolution_option_id=option_id,
                    approved_by="HUMAN_OPERATOR",
                )
                data.invalidate()
                st.rerun()
            except Exception as err:
                _show_failure("The approved action could not be executed. Check the audit trail before retrying.", err)

    if rejected:
        with st.spinner("Recording the rejection…"):
            try:
                ResolutionService.reject_resolution(
                    exception_id=exception_id,
                    resolution_option_id=option_id,
                    rejected_by="HUMAN_OPERATOR",
                    reason="Rejected by operator in the RELAY exception workspace.",
                )
                data.invalidate()
                st.rerun()
            except Exception as err:
                _show_failure("The rejection could not be recorded. Please try again.", err)

    return exc


# ---------------------------------------------------------------------------
# Stage 6/7 — execution and verification
# ---------------------------------------------------------------------------

def _verification_stage(exc: Dict[str, Any], exception_id: str, exec_key: str) -> None:
    # Only the current decision cycle's execution belongs here — an exception that has
    # been re-investigated or re-resolved since a prior approval carries stale action rows
    # that would otherwise be shown next to a fresh, still-pending approval gate.
    if exc.get("status") != "RESOLVED":
        return

    try:
        past = ExceptionQueries.get_actions_for_exception(exception_id) or []
    except Exception:
        past = []
    cached = st.session_state.get(exec_key)
    if not past and not cached:
        return

    section("4 · Execution & verification", "Read back from the database after the write")

    if cached is not None:
        action_type = _field(cached, "action_type")
        message = _field(cached, "result_message")
        changes = _field(cached, "verified_db_changes", {})
        executed_at = _field(cached, "executed_at")
        executed_by = "HUMAN_OPERATOR"
        state = _field(cached, "status", "SUCCESS")
    else:
        action = past[0]
        action_type = action.get("action_type")
        message = action.get("result_message")
        payload = action.get("payload") or {}
        changes = payload.get("verified_changes") or payload
        executed_at = action.get("executed_at")
        executed_by = action.get("executed_by")
        state = action.get("execution_status")

    st.markdown(
        '<div class="callout good"><div class="callout-title">Action executed</div>'
        f'<div class="callout-body"><b>{action_type}</b> — {message}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="card"><div class="card-body">'
        + detail_grid(
            [
                ("Action type", mono(action_type)),
                ("Execution state", badge(state)),
                ("Executed by", str(executed_by or "—")),
                ("Executed at", format_datetime(executed_at)),
            ]
        )
        + "</div></div>",
        unsafe_allow_html=True,
    )
    if changes:
        with st.expander("Verified database state change"):
            st.json(changes)

    if len(past) > 1:
        section("Earlier actions on this exception")
        st.markdown(
            data_table(
                [
                    Col("Action", render=lambda r: mono(r.get("action_type")), strong=True),
                    Col("State", render=lambda r: badge(r.get("execution_status"))),
                    Col("By", key="executed_by"),
                    Col("When", render=lambda r: format_datetime(r.get("executed_at"))),
                    Col("Result", render=lambda r: str(r.get("result_message") or "—")[:80]),
                ],
                past[1:],
            ),
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Agent trace for this exception
# ---------------------------------------------------------------------------

def _trace_stage(exc: Dict[str, Any]) -> None:
    logs = exc.get("audit_logs") or []
    if not logs:
        return
    spacer(0.6)
    with st.expander(f"Audit trail for this exception · {len(logs)} entries"):
        st.markdown(
            data_table(
                [
                    Col("Step", render=lambda r: title_case(r.get("agent_step")), strong=True),
                    Col("Tool", render=lambda r: mono(r.get("tool_called")) if r.get("tool_called") else "—"),
                    Col("Decision", render=lambda r: str(r.get("decision") or "—")[:90]),
                    Col(
                        "Approval",
                        render=lambda r: badge(r.get("human_approval_status"))
                        if r.get("human_approval_status")
                        else "—",
                    ),
                    Col("Recorded", render=lambda r: format_datetime(r.get("created_at"))),
                ],
                logs,
            ),
            unsafe_allow_html=True,
        )
