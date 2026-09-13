"""
Chart builders.

Conventions (kept deliberately narrow so every chart in RELAY reads the same):
  · magnitude by identity → horizontal bars, one hue, direct value labels
  · state distributions   → horizontal bars in the fixed status palette, with the
                            state named on the axis so colour never carries meaning alone
  · one value axis only, recessive grid, tabular tick figures
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import plotly.graph_objects as go

from app.theme import (
    INK_900,
    SERIES_BLUE,
    STATUS_CRITICAL,
    STATUS_GOOD,
    STATUS_SERIOUS,
    STATUS_WARNING,
    style_chart,
)

# Operational state → mark colour. Reserved: never reused as a series colour.
STATE_COLORS = {
    "HEALTHY": STATUS_GOOD,
    "DELIVERED": STATUS_GOOD,
    "RECEIVED": STATUS_GOOD,
    "RESOLVED": STATUS_GOOD,
    "APPROVED": STATUS_GOOD,
    "CONFIRMED": SERIES_BLUE,
    "IN_TRANSIT": SERIES_BLUE,
    "OUT_FOR_DELIVERY": SERIES_BLUE,
    "ISSUED": SERIES_BLUE,
    "CREATED": "#98A2B3",
    "OPEN": "#98A2B3",
    "CANCELLED": "#98A2B3",
    "IGNORED": "#98A2B3",
    "INVESTIGATING": STATUS_WARNING,
    "REROUTED": STATUS_WARNING,
    "MEDIUM": STATUS_WARNING,
    "EXPEDITED": STATUS_SERIOUS,
    "HIGH": STATUS_SERIOUS,
    "PENDING_APPROVAL": STATUS_SERIOUS,
    "DELAYED": STATUS_CRITICAL,
    "CRITICAL": STATUS_CRITICAL,
    "EXCEPTION": STATUS_CRITICAL,
    "REJECTED": STATUS_CRITICAL,
}

_BAR_HEIGHT = 34
_MIN_HEIGHT = 150


def _height(count: int) -> int:
    return max(_MIN_HEIGHT, count * _BAR_HEIGHT + 40)


def _label(value: str) -> str:
    return str(value).replace("_", " ").title()


def counts_of(rows: Sequence[Dict[str, Any]], field: str) -> List[Tuple[str, int]]:
    """Count rows by a field, most frequent first."""
    tally: Dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "UNKNOWN").upper()
        tally[key] = tally.get(key, 0) + 1
    return sorted(tally.items(), key=lambda item: item[1], reverse=True)


def magnitude_bars(pairs: Sequence[Tuple[str, float]], value_suffix: str = ""):
    """Single-hue horizontal bars for 'how many / how much by category'."""
    pairs = list(pairs)[:8]
    labels = [_label(name) for name, _ in pairs][::-1]
    values = [value for _, value in pairs][::-1]
    text = [f"{v:,.0f}{value_suffix}" for v in values]
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker=dict(color=SERIES_BLUE, cornerradius=4),
            text=text,
            textposition="outside",
            textfont=dict(size=11, color=INK_900),
            cliponaxis=False,
            hovertemplate="%{y}: <b>%{x:,.0f}</b>" + value_suffix + "<extra></extra>",
        )
    )
    fig = style_chart(fig, height=_height(len(pairs)), show_grid="none")
    fig.update_xaxes(showticklabels=False, range=[0, (max(values) if values else 1) * 1.22])
    return fig


def state_bars(pairs: Sequence[Tuple[str, float]]):
    """Horizontal bars coloured by operational state, state named on the axis."""
    pairs = list(pairs)[:8]
    labels = [_label(name) for name, _ in pairs][::-1]
    values = [value for _, value in pairs][::-1]
    colors = [STATE_COLORS.get(str(name).upper(), "#98A2B3") for name, _ in pairs][::-1]
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker=dict(color=colors, cornerradius=4),
            text=[f"{v:,.0f}" for v in values],
            textposition="outside",
            textfont=dict(size=11, color=INK_900),
            cliponaxis=False,
            hovertemplate="%{y}: <b>%{x:,.0f}</b><extra></extra>",
        )
    )
    fig = style_chart(fig, height=_height(len(pairs)), show_grid="none")
    fig.update_xaxes(showticklabels=False, range=[0, (max(values) if values else 1) * 1.22])
    return fig


def stock_position(rows: Sequence[Dict[str, Any]], limit: int = 7):
    """Available units per stock line, with the reorder point marked.

    Two marks, so the caller pairs this with `ui.legend([...])` — identity is
    never left to colour alone.
    """
    rows = list(rows)[:limit][::-1]
    labels = [
        f"{str(r.get('product_name') or '')[:22]} · {str(r.get('warehouse_city') or '')[:12]}"
        for r in rows
    ]
    available = [float(r.get("quantity_available") or 0) for r in rows]
    reorder = [float(r.get("reorder_point") or 0) for r in rows]
    safety = [float(r.get("safety_stock") or 0) for r in rows]
    colors = []
    for qty, rp, ss in zip(available, reorder, safety):
        if qty <= ss:
            colors.append(STATUS_CRITICAL)
        elif qty <= rp:
            colors.append(STATUS_WARNING)
        else:
            colors.append(STATUS_GOOD)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=available,
            y=labels,
            orientation="h",
            marker=dict(color=colors, cornerradius=4),
            text=[f"{v:,.0f}" for v in available],
            textposition="outside",
            textfont=dict(size=11, color=INK_900),
            cliponaxis=False,
            hovertemplate="%{y}<br>Available: <b>%{x:,.0f}</b><extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=reorder,
            y=labels,
            mode="markers",
            marker=dict(
                symbol="line-ns",
                size=16,
                line=dict(color=INK_900, width=2),
            ),
            hovertemplate="Reorder point: <b>%{x:,.0f}</b><extra></extra>",
        )
    )
    upper = max(available + reorder + [1]) * 1.2
    fig = style_chart(fig, height=_height(len(rows)), show_grid="none")
    fig.update_xaxes(showticklabels=False, range=[0, upper])
    return fig


def exposure_bars(rows: Sequence[Dict[str, Any]], limit: int = 6):
    """Financial exposure per exception — magnitude, single hue, USD labels."""
    ranked = sorted(
        rows,
        key=lambda r: float(r.get("estimated_financial_loss") or 0),
        reverse=True,
    )[:limit][::-1]
    labels = [str(r.get("exception_code") or "")[:18] for r in ranked]
    values = [float(r.get("estimated_financial_loss") or 0) for r in ranked]
    titles = [str(r.get("title") or "") for r in ranked]
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker=dict(color=SERIES_BLUE, cornerradius=4),
            text=[
                f"${v / 1e6:,.1f}M" if v >= 1e6 else (f"${v / 1e3:,.1f}K" if v >= 1e3 else f"${v:,.0f}")
                for v in values
            ],
            textposition="outside",
            textfont=dict(size=11, color=INK_900),
            cliponaxis=False,
            customdata=titles,
            hovertemplate="%{customdata}<br>Exposure: <b>$%{x:,.0f}</b><extra></extra>",
        )
    )
    fig = style_chart(fig, height=_height(len(ranked)), show_grid="none")
    fig.update_xaxes(showticklabels=False, range=[0, (max(values) if values else 1) * 1.28])
    return fig
