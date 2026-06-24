"""Holdings summary strip — total value, day change, unrealized P/L."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import streamlit as st

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_holdings_summary import HoldingsSummary, compute_holdings_summary

if TYPE_CHECKING:
    from services.portfolio_month_dividends import CurrentMonthPaidDividends


def _format_delta(value: Optional[float], pct: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if pct is not None:
        return f"{pct:+.2f}%"
    return None


def _metric_columns(count: int) -> list:
    """Lay out metrics in rows that avoid cramped single-line overlap."""
    if count <= 3:
        return list(st.columns(count))
    if count == 4:
        row_a, row_b = st.columns(2)
        row_c, row_d = st.columns(2)
        return [row_a, row_b, row_c, row_d]
    row_a, row_b, row_c = st.columns(3)
    row_d, row_e = st.columns(2)
    return [row_a, row_b, row_c, row_d, row_e]


def render_holdings_summary(
    rows: List[PortfolioDetailRow],
    *,
    summary: Optional[HoldingsSummary] = None,
    show_positions: bool = False,
    month_paid: Optional["CurrentMonthPaidDividends"] = None,
    show_month_received: bool = False,
) -> HoldingsSummary:
    """Render broker-style holdings summary metrics."""
    if summary is None and rows and any(row.previous_close is None for row in rows):
        from services.portfolio_details_service import PortfolioDetailsService

        rows = PortfolioDetailsService().enrich_rows_previous_close(rows)
        try:
            st.session_state["portfolio_details_rows"] = rows
        except Exception:  # noqa: S110
            pass

    metrics = summary or compute_holdings_summary(rows)
    include_received = show_month_received and month_paid is not None

    metric_count = 3 + int(show_positions) + int(include_received)
    metric_columns = _metric_columns(metric_count)

    index = 0
    if show_positions:
        metric_columns[index].metric("Positions", metrics.positions)
        index += 1

    metric_columns[index].metric(
        "Total value",
        f"${metrics.total_value_usd:,.2f}",
    )
    index += 1

    if include_received and index < len(metric_columns):
        received = month_paid
        value = f"${received.gross_usd:,.2f}"
        payer_delta = (
            f"{received.payer_count} payment{'s' if received.payer_count != 1 else ''}"
            if received.payer_count
            else "None yet"
        )
        net_hint = (
            f" · net ${received.net_usd:,.2f} est."
            if received.net_usd is not None and received.gross_usd > 0
            else ""
        )
        metric_columns[index].metric(
            f"Received ({received.month_label.split()[0]})",
            value,
            f"{received.through_label} · {payer_delta}{net_hint}",
            help=(
                f"Gross cash received with pay date in {received.month_label}, "
                f"on or before {received.through_date.strftime('%d %b %Y')}. "
                "Shares on ex-date from your purchase journal when available — "
                "same basis as Yahoo portfolio dividends."
                + (
                    f" Net after withholding (est.) ${received.net_usd:,.2f}."
                    if received.net_usd is not None
                    else ""
                )
            ),
        )
        index += 1

    day_delta = _format_delta(metrics.day_change_usd, metrics.day_change_pct)
    if metrics.day_change_usd is not None:
        metric_columns[index].metric(
            "Day change",
            f"${metrics.day_change_usd:+,.2f}",
            day_delta,
        )
    else:
        metric_columns[index].metric("Day change", "—", help="Reload live data for today's move")
    index += 1

    gl_delta = _format_delta(metrics.unrealized_gl_usd, metrics.unrealized_gl_pct)
    metric_columns[index].metric(
        "Unrealized G/L",
        f"${metrics.unrealized_gl_usd:+,.2f}",
        gl_delta,
    )

    return metrics
