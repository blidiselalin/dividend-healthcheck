"""Holdings summary strip — total value, day change, unrealized P/L."""

from __future__ import annotations

from typing import List, Optional

import streamlit as st

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_holdings_summary import HoldingsSummary, compute_holdings_summary


def _format_delta(value: Optional[float], pct: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if pct is not None:
        return f"{pct:+.2f}%"
    return None


def render_holdings_summary(
    rows: List[PortfolioDetailRow],
    *,
    summary: Optional[HoldingsSummary] = None,
    show_positions: bool = False,
) -> HoldingsSummary:
    """Render broker-style holdings summary metrics."""
    metrics = summary or compute_holdings_summary(rows)

    columns = st.columns(4 if show_positions else 3)
    index = 0
    if show_positions:
        columns[index].metric("Positions", metrics.positions)
        index += 1

    columns[index].metric(
        "Holdings Summary",
        f"${metrics.total_value_usd:,.2f}",
    )
    index += 1

    day_delta = _format_delta(metrics.day_change_usd, metrics.day_change_pct)
    if metrics.day_change_usd is not None:
        columns[index].metric(
            "Day Change",
            f"${metrics.day_change_usd:+,.2f}",
            day_delta,
        )
    else:
        columns[index].metric("Day Change", "—", help="Reload live data for today's move")
    index += 1

    gl_delta = _format_delta(metrics.unrealized_gl_usd, metrics.unrealized_gl_pct)
    columns[index].metric(
        "Unrealized G/L",
        f"${metrics.unrealized_gl_usd:+,.2f}",
        gl_delta,
    )

    return metrics
