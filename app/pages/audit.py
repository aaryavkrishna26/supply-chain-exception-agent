"""
Audit trail — every agent step, tool call, human decision and executed action,
in the order the system recorded them.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from app import charts, data
from app.ui import (
    Col,
    badge,
    card_container,
    data_table,
    detail_grid,
    empty_state,
    format_datetime,
    kpi_row,
    mono,
    page_header,
    section,
    title_case,
)

_DECISION_STEPS = ("HUMAN_APPROVAL", "APPROVAL", "HUMAN_DECISION", "REJECTION")


def render_audit_page() -> None:
    head, action = st.columns([3, 1])
    with head:
        page_header(
            "Audit trail",
            "Immutable record of what the agent looked at, what it concluded, what a "
            "human decided and what was written back.",
            eyebrow="Governance",
            bordered=False,
        )
    with action:
        st.markdown('<div style="height:1.6rem"></div>', unsafe_allow_html=True)
        if st.button("Refresh", width="stretch"):
            data.invalidate()
            st.rerun()
    st.markdown('<div class="page-divider"></div>', unsafe_allow_html=True)

    logs: List[Dict[str, Any]] = data.audit_logs(limit=400)
    executed = data.actions()

    if not logs:
        empty_state(
            "Nothing recorded yet",
            "Investigate an exception to start the trail.",
            icon="○",
        )
        return

    tool_calls = [log for log in logs if log.get("tool_called")]
    decisions = [
        log
        for log in logs
        if log.get("human_approval_status")
        or str(log.get("agent_step") or "").upper() in _DECISION_STEPS
    ]
    kpi_row(
        [
            {"label": "Trail entries", "value": len(logs)},
            {"label": "Tool invocations", "value": len(tool_calls)},
            {
                "label": "Human decisions",
                "value": len(decisions),
                "tone": "accent" if decisions else None,
            },
            {
                "label": "Actions executed",
                "value": len(executed),
                "meta": f"{len([a for a in executed if a.get('execution_status') == 'SUCCESS'])} succeeded",
                "tone": "good" if executed else None,
            },
            {
                "label": "Exceptions covered",
                "value": len({log.get("exception_id") for log in logs if log.get("exception_id")}),
            },
        ],
        per_row=5,
    )

    exception_labels = {"All exceptions": None}
    for log in logs:
        code = log.get("exception_code")
        if code and code not in exception_labels:
            exception_labels[f"{code} · {str(log.get('exception_title') or '')[:44]}"] = log.get(
                "exception_id"
            )

    picker, step_filter = st.columns([2, 2])
    with picker:
        chosen = st.selectbox("Exception", list(exception_labels.keys()))
        exception_id = exception_labels[chosen]
    with step_filter:
        steps = sorted({str(log.get("agent_step") or "").upper() for log in logs if log.get("agent_step")})
        chosen_step = st.selectbox("Agent step", ["All steps"] + [title_case(s) for s in steps])

    filtered = logs
    if exception_id:
        filtered = [log for log in filtered if log.get("exception_id") == exception_id]
    if chosen_step != "All steps":
        filtered = [
            log
            for log in filtered
            if title_case(log.get("agent_step")) == chosen_step
        ]

    left, right = st.columns(2)
    with left:
        section("Trail composition", "Agent steps recorded")
        with card_container("audit_steps"):
            st.plotly_chart(
                charts.magnitude_bars(charts.counts_of(logs, "agent_step")),
                width="stretch",
                config={"displayModeBar": False},
            )
    with right:
        section("Most-invoked tools", "Across every investigation")
        tool_counts = charts.counts_of(tool_calls, "tool_called")[:7]
        st.markdown(
            '<div class="card"><div class="card-body tight">'
            + data_table(
                [
                    Col("Tool", render=lambda r: mono(r["name"]), strong=True, nowrap=True),
                    Col("Calls", render=lambda r: str(r["count"]), align="num"),
                ],
                [{"name": name, "count": count} for name, count in tool_counts],
            )
            + "</div></div>",
            unsafe_allow_html=True,
        )

    section("Trail", f"{len(filtered)} of {len(logs)} entries")
    st.markdown(
        data_table(
            [
                Col(
                    "Step",
                    render=lambda r: (
                        f'<span>{title_case(r.get("agent_step"))}</span>'
                        f'<span class="sub">{r.get("exception_code") or "—"}</span>'
                    ),
                    strong=True,
                ),
                Col(
                    "Tool",
                    render=lambda r: mono(r.get("tool_called")) if r.get("tool_called") else "—",
                ),
                Col("Decision", render=lambda r: str(r.get("decision") or "—")[:150]),
                Col(
                    "Approval",
                    render=lambda r: badge(r.get("human_approval_status"))
                    if r.get("human_approval_status")
                    else "—",
                ),
                Col("Recorded", render=lambda r: format_datetime(r.get("created_at")), nowrap=True),
            ],
            filtered[:120],
        ),
        unsafe_allow_html=True,
    )
    if executed:
        section("Executed actions", "Writes applied to the operational record")
        st.markdown(
            data_table(
                [
                    Col("Action", render=lambda r: mono(r.get("action_type")), strong=True),
                    Col(
                        "Exception",
                        render=lambda r: (
                            f'<span>{r.get("exception_code") or "—"}</span>'
                            f'<span class="sub">{str(r.get("exception_title") or "")[:44]}</span>'
                        ),
                    ),
                    Col("State", render=lambda r: badge(r.get("execution_status"))),
                    Col("By", key="executed_by"),
                    Col("Result", render=lambda r: str(r.get("result_message") or "—")[:90]),
                    Col("When", render=lambda r: format_datetime(r.get("executed_at"))),
                ],
                executed,
            ),
            unsafe_allow_html=True,
        )

    section("Inspect an entry", "Full tool input and output as stored")
    entry_labels = {
        f"{title_case(log.get('agent_step'))} · {log.get('tool_called') or 'no tool'} · "
        f"{format_datetime(log.get('created_at'))}": log
        for log in filtered[:60]
    }
    if entry_labels:
        selected = entry_labels[st.selectbox("Entry", list(entry_labels.keys()), label_visibility="collapsed")]
        st.markdown(
            '<div class="card"><div class="card-body">'
            + detail_grid(
                [
                    ("Agent step", title_case(selected.get("agent_step"))),
                    ("Tool called", mono(selected.get("tool_called")) if selected.get("tool_called") else "—"),
                    ("Exception", mono(selected.get("exception_code"))),
                    ("Severity", badge(selected.get("exception_severity"))),
                    ("Approval status", badge(selected.get("human_approval_status")) if selected.get("human_approval_status") else "—"),
                    ("Recorded", format_datetime(selected.get("created_at"))),
                ]
            )
            + (
                f'<div class="callout" style="margin-top:.9rem"><div class="callout-title">Decision</div>'
                f'<div class="callout-body">{selected.get("decision")}</div></div>'
                if selected.get("decision")
                else ""
            )
            + (
                f'<div class="callout" style="margin-top:.6rem"><div class="callout-title">Notes</div>'
                f'<div class="callout-body">{selected.get("notes")}</div></div>'
                if selected.get("notes")
                else ""
            )
            + "</div></div>",
            unsafe_allow_html=True,
        )
        payload_in, payload_out = st.columns(2)
        with payload_in:
            st.caption("Tool input")
            st.json(selected.get("input_payload") or {})
        with payload_out:
            st.caption("Tool output")
            st.json(selected.get("output_payload") or {})
