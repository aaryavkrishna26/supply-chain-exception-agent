"""
RELAY UI component library.

Every page composes its layout from these helpers so that spacing, typography
and status colour stay consistent. All markup here targets the classes declared
in `app/theme.py` — pages should not write raw styles.
"""

from __future__ import annotations

import html
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import streamlit as st

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

DASH = "—"


def esc(value: Any) -> str:
    """HTML-escape a value for safe interpolation into component markup."""
    if value is None:
        return DASH
    return html.escape(str(value))


def format_currency(value: Any, compact: bool = False) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return DASH
    if compact:
        for size, suffix, digits in ((1e9, "B", 2), (1e6, "M", 2), (1e3, "K", 1)):
            if abs(amount) >= size:
                return f"${amount / size:,.{digits}f}{suffix}"
    if abs(amount) < 1_000:
        return f"${amount:,.2f}"  # unit costs need their cents
    return f"${amount:,.0f}"


def format_number(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return DASH


def format_percent(value: Any, decimals: int = 0) -> str:
    try:
        return f"{float(value):.{decimals}f}%"
    except (TypeError, ValueError):
        return DASH


def format_date(value: Any) -> str:
    if not value:
        return DASH
    return str(value)[:10]


def format_datetime(value: Any) -> str:
    if not value:
        return DASH
    return str(value)[:16].replace("T", " ")


def title_case(value: Any) -> str:
    if value in (None, ""):
        return DASH
    return str(value).replace("_", " ").title()


def initials(name: str) -> str:
    parts = [p for p in str(name or "").split() if p]
    if not parts:
        return "U"
    return "".join(p[0].upper() for p in parts[:2])


# ---------------------------------------------------------------------------
# Status vocabulary → badge tone
# ---------------------------------------------------------------------------

_TONE_MAP = {
    # exception lifecycle
    "OPEN": "neutral",
    "INVESTIGATING": "warning",
    "PENDING_APPROVAL": "serious",
    "APPROVED": "good",
    "RESOLVED": "good",
    "REJECTED": "critical",
    "IGNORED": "neutral",
    # severity / risk
    "LOW": "good",
    "MEDIUM": "warning",
    "HIGH": "serious",
    "CRITICAL": "solid",
    # shipments
    "CREATED": "neutral",
    "IN_TRANSIT": "info",
    "OUT_FOR_DELIVERY": "info",
    "DELIVERED": "good",
    "DELAYED": "critical",
    "REROUTED": "warning",
    "EXCEPTION": "critical",
    "CANCELLED": "neutral",
    # purchase orders
    "ISSUED": "info",
    "CONFIRMED": "info",
    "RECEIVED": "good",
    "EXPEDITED": "serious",
    # inventory
    "HEALTHY": "good",
    "REORDER": "warning",
    "STOCKOUT": "critical",
    # generic
    "ACTIVE": "good",
    "INACTIVE": "neutral",
    "YES": "good",
    "NO": "neutral",
    "SUCCESS": "good",
    "FAILED": "critical",
    "PENDING": "warning",
    "ON_TIME": "good",
}


def badge(value: Any, tone: Optional[str] = None, dot: bool = True) -> str:
    """Status pill.

    Tone is derived from the value unless given explicitly. Database-style codes
    (`PENDING_APPROVAL`) are normalised for display; prose labels ("18h late")
    are left exactly as written.
    """
    if value in (None, ""):
        return f'<span class="badge badge-neutral nodot">{DASH}</span>'
    text = str(value).strip()
    key = text.upper().replace(" ", "_")
    resolved = tone or _TONE_MAP.get(key, "neutral")
    label = text.replace("_", " ").title() if (text.isupper() or "_" in text) else text
    cls = f"badge badge-{resolved}" + ("" if dot else " nodot")
    return f'<span class="{cls}">{esc(label)}</span>'


def mono(value: Any) -> str:
    if value in (None, ""):
        return DASH
    return f'<span class="mono">{esc(value)}</span>'


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------

def page_header(
    title: str,
    subtitle: Optional[str] = None,
    eyebrow: Optional[str] = None,
    meta: Optional[str] = None,
    bordered: bool = True,
) -> None:
    """Page title block.

    `meta` renders as right-aligned supporting markup. Pass `bordered=False`
    when the header shares a row with widget columns, then call `divider()`
    underneath so the rule spans the full page width.
    """
    left = ""
    if eyebrow:
        left += f'<div class="page-eyebrow">{esc(eyebrow)}</div>'
    left += f'<div class="page-title">{esc(title)}</div>'
    if subtitle:
        left += f'<div class="page-sub">{esc(subtitle)}</div>'
    right = f'<div class="page-meta">{meta}</div>' if meta else ""
    cls = "page-head" if bordered else "page-head flat"
    st.markdown(
        f'<div class="{cls}"><div>{left}</div>{right}</div>',
        unsafe_allow_html=True,
    )


def divider() -> None:
    st.markdown('<div class="page-divider"></div>', unsafe_allow_html=True)


def section(title: str, note: Optional[str] = None) -> None:
    right = f'<div class="section-note">{esc(note)}</div>' if note else ""
    st.markdown(
        f'<div class="section-head"><div class="section-title">{esc(title)}</div>{right}</div>',
        unsafe_allow_html=True,
    )


def spacer(rem: float = 1.0) -> None:
    st.markdown(f'<div style="height:{rem}rem"></div>', unsafe_allow_html=True)


def kpi_row(items: Sequence[Dict[str, Any]], per_row: Optional[int] = None) -> None:
    """Grid of KPI tiles.

    Each item: {label, value, meta?, tone?} where tone ∈
    accent | critical | warning | good | (none).
    """
    if not items:
        return
    columns = per_row or min(len(items), 6)
    tiles = []
    for item in items:
        tone = item.get("tone")
        cls = "kpi" + (f" is-{tone}" if tone else "")
        meta = f'<div class="kpi-meta">{item.get("meta")}</div>' if item.get("meta") else ""
        tiles.append(
            f'<div class="{cls}"><div class="kpi-label">{esc(item.get("label"))}</div>'
            f'<div class="kpi-value">{item.get("value")}</div>{meta}</div>'
        )
    st.markdown(
        f'<div class="kpi-row" style="grid-template-columns:repeat({columns},minmax(0,1fr))">'
        + "".join(tiles)
        + "</div>",
        unsafe_allow_html=True,
    )


def card(title: Optional[str], body_html: str, action_html: str = "") -> None:
    """Static content card. For cards that hold Streamlit widgets, use
    `st.container(border=True)` instead."""
    head = ""
    if title:
        head = (
            f'<div class="card-head"><div class="card-title">{esc(title)}</div>'
            f"<div>{action_html}</div></div>"
        )
    st.markdown(
        f'<div class="card">{head}<div class="card-body">{body_html}</div></div>',
        unsafe_allow_html=True,
    )


def card_container(key: str):
    """Bordered card that can hold Streamlit widgets (charts, buttons, inputs).

    The `key` surfaces as an `st-key-card_<key>` class, which `app/theme.py`
    styles as a card — Streamlit's own container classes are not stable.
    """
    return st.container(border=True, key=f"card_{key}")


def callout(title: str, body_html: str, tone: str = "") -> None:
    cls = "callout" + (f" {tone}" if tone else "")
    st.markdown(
        f'<div class="{cls}"><div class="callout-title">{esc(title)}</div>'
        f'<div class="callout-body">{body_html}</div></div>',
        unsafe_allow_html=True,
    )


def detail_grid(items: Sequence[tuple]) -> str:
    """Label/value grid markup. Values may contain markup."""
    cells = "".join(
        f'<div class="detail-item"><div class="detail-label">{esc(label)}</div>'
        f'<div class="detail-value">{value}</div></div>'
        for label, value in items
    )
    return f'<div class="detail-grid">{cells}</div>'


def empty_state(title: str, text: str = "", icon: str = "○") -> None:
    st.markdown(
        f'<div class="empty"><div class="empty-icon">{esc(icon)}</div>'
        f'<div class="empty-title">{esc(title)}</div>'
        f'<div class="empty-text">{esc(text)}</div></div>',
        unsafe_allow_html=True,
    )


def meter(fraction: float, tone: str = "") -> str:
    pct = max(0.0, min(1.0, float(fraction or 0))) * 100
    cls = "meter" + (f" {tone}" if tone else "")
    return f'<div class="{cls}"><span style="width:{pct:.0f}%"></span></div>'


def legend(items: Sequence[tuple]) -> None:
    """items: [(label, hex)] — identity is never carried by colour alone."""
    body = "".join(
        f'<span class="legend-item"><span class="legend-swatch" style="background:{color}"></span>'
        f"{esc(label)}</span>"
        for label, color in items
    )
    st.markdown(f'<div class="legend">{body}</div>', unsafe_allow_html=True)


def stages(all_stages: Sequence[str], current: Optional[str]) -> None:
    """Lifecycle progress bar: everything before `current` reads as done."""
    try:
        idx = list(all_stages).index(current) if current else -1
    except ValueError:
        idx = -1
    cells = []
    for i, name in enumerate(all_stages):
        cls = "stage"
        if idx >= 0 and i < idx:
            cls += " done"
        elif i == idx:
            cls += " active"
        cells.append(
            f'<div class="{cls}"><span class="stage-i">{i + 1:02d}</span>{esc(name)}</div>'
        )
    st.markdown(f'<div class="stages">{"".join(cells)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class Col:
    """Table column spec.

    label   header text
    key     record key (ignored when `render` is supplied)
    render  callable(record) -> markup
    align   "left" | "num" (right-aligned, tabular figures)
    strong  emphasise the cell as the row's identifier
    nowrap  keep the cell on one line (identifiers, dates, badges)
    """

    def __init__(
        self,
        label: str,
        key: Optional[str] = None,
        render: Optional[Callable[[Dict[str, Any]], str]] = None,
        align: str = "left",
        strong: bool = False,
        nowrap: bool = False,
    ):
        self.label = label
        self.key = key
        self.render = render
        self.align = align
        self.strong = strong
        self.nowrap = nowrap

    def cell(self, record: Dict[str, Any]) -> str:
        if self.render is not None:
            return self.render(record)
        value = record.get(self.key) if self.key else None
        return esc(value) if value not in (None, "") else DASH


def data_table(columns: Sequence[Col], rows: Iterable[Dict[str, Any]]) -> str:
    """Render a records list as RELAY's table markup (returns the markup)."""
    head = "".join(
        f'<th class="{"num" if c.align == "num" else ""}">{esc(c.label)}</th>' for c in columns
    )
    body: List[str] = []
    for record in rows:
        cells = []
        for col in columns:
            css = []
            if col.align == "num":
                css.append("num")
            if col.strong:
                css.append("strong")
            if col.nowrap:
                css.append("nw")
            attr = f' class="{" ".join(css)}"' if css else ""
            cells.append(f"<td{attr}>{col.cell(record)}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    if not body:
        body.append(
            f'<tr><td colspan="{len(columns)}" style="text-align:center;color:#667085;'
            f'padding:1.6rem">No records</td></tr>'
        )
    return (
        '<div class="tbl-wrap"><table class="tbl"><thead><tr>'
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def table_card(
    title: str,
    columns: Sequence[Col],
    rows: Iterable[Dict[str, Any]],
    note: str = "",
) -> None:
    """A table wrapped in a titled card."""
    action = f'<div class="section-note">{esc(note)}</div>' if note else ""
    head = (
        f'<div class="card-head"><div class="card-title">{esc(title)}</div>{action}</div>'
        if title
        else ""
    )
    st.markdown(
        f'<div class="card">{head}<div class="card-body tight">'
        + data_table(columns, rows)
        + "</div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Domain helpers shared by several pages
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# List controls — search, filter and sort, shared by every table page
# ---------------------------------------------------------------------------

def _sort_value(value: Any) -> tuple:
    """Comparable key for one cell: numbers by value, dates by instant, text case-insensitively."""
    if isinstance(value, bool):
        return (float(value), "")
    if isinstance(value, (int, float, Decimal)):
        return (float(value), "")
    if isinstance(value, datetime):
        return (value.timestamp(), "")
    if isinstance(value, date):
        return (datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp(), "")
    return (0.0, str(value).strip().lower())


def sort_rows(rows: Sequence[Dict[str, Any]], field: str, descending: bool = False) -> List[Dict[str, Any]]:
    """Sort by one field, always leaving rows that have no value for it last."""
    present = [r for r in rows if r.get(field) is not None]
    missing = [r for r in rows if r.get(field) is None]
    present.sort(key=lambda row: _sort_value(row.get(field)), reverse=descending)
    return present + missing


def search_rows(rows: Sequence[Dict[str, Any]], query: str, fields: Sequence[str]) -> List[Dict[str, Any]]:
    """Case-insensitive substring match across the given fields."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(rows)
    return [r for r in rows if any(needle in str(r.get(f) or "").lower() for f in fields)]


def list_controls(
    rows: Sequence[Dict[str, Any]],
    key: str,
    search_fields: Sequence[str],
    placeholder: str = "Search",
    views: Optional[Dict[str, Sequence[Dict[str, Any]]]] = None,
    default_view: Optional[str] = None,
    filters: Sequence[tuple] = (),
    sorts: Sequence[tuple] = (),
) -> List[Dict[str, Any]]:
    """Draw one row of search / filter / sort controls and return the matching rows.

    views    {label: subset}            — segmented control over pre-computed subsets
    filters  (label, field, any_label)  — a dropdown whose options come from the data
    sorts    (label, field, descending) — a dropdown of sort orders

    Filter options are built from the full row set, so narrowing the list never
    makes the option you want disappear.
    """
    pool: List[Dict[str, Any]] = list(rows)

    # The view chips get their own full-width row: crowded into a column with the
    # dropdowns, longer labels get clipped.
    if views:
        labels = list(views)
        fallback = default_view if default_view in views else labels[0]
        chosen = st.segmented_control(
            "View", labels, default=fallback, key=f"{key}_view", label_visibility="collapsed"
        ) or fallback
        pool = list(views.get(chosen, rows))

    widths: List[float] = [1.8]
    widths += [1.0] * len(filters)
    if sorts:
        widths.append(1.2)
    columns = st.columns(widths)
    position = 0

    with columns[position]:
        query = st.text_input(
            "Search", placeholder=placeholder, key=f"{key}_search", label_visibility="collapsed"
        )
    position += 1
    pool = search_rows(pool, query, search_fields)

    for label, field, any_label in filters:
        options = [any_label] + sorted({str(r.get(field)) for r in rows if r.get(field) not in (None, "")})
        with columns[position]:
            chosen = st.selectbox(label, options, key=f"{key}_{field}", label_visibility="collapsed")
        position += 1
        if chosen != any_label:
            pool = [r for r in pool if str(r.get(field)) == chosen]

    if sorts:
        order = {label: (field, descending) for label, field, descending in sorts}
        with columns[position]:
            chosen = st.selectbox("Sort", list(order), key=f"{key}_sort", label_visibility="collapsed")
        field, descending = order[chosen]
        pool = sort_rows(pool, field, descending)

    return pool


def inventory_state(available: Any, reorder_point: Any, safety_stock: Any) -> str:
    """Classify a stock position the same way everywhere."""
    try:
        qty = float(available or 0)
        reorder = float(reorder_point or 0)
        safety = float(safety_stock or 0)
    except (TypeError, ValueError):
        return "HEALTHY"
    if qty <= safety:
        return "CRITICAL"
    if qty <= reorder:
        return "LOW"
    return "HEALTHY"


def delay_label(hours: Any) -> str:
    try:
        value = int(float(hours or 0))
    except (TypeError, ValueError):
        return badge("On time")
    if value <= 0:
        return badge("On time", tone="good")
    if value >= 24:
        days = value / 24
        return badge(f"{days:.1f}d late", tone="critical")
    return badge(f"{value}h late", tone="serious")


def risk_from_reliability(rating: Any) -> str:
    try:
        value = float(rating or 0)
    except (TypeError, ValueError):
        return "MEDIUM"
    if value >= 0.95:
        return "LOW"
    if value >= 0.85:
        return "MEDIUM"
    return "HIGH"


def safe_query(fn: Callable, *args, **kwargs):
    """Run a data-access call, returning [] instead of raising into the UI."""
    try:
        result = fn(*args, **kwargs)
        return result if result is not None else []
    except Exception:
        return []
