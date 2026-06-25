"""Holdings summary strip — total value, day change, unrealized P/L."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import streamlit as st

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_holdings_summary import HoldingsSummary, compute_holdings_summary
from ui.design_system import (
    close_dividend_focus_panel,
    close_panel,
    open_dividend_focus_panel,
    open_panel,
    render_metric_grid,
    render_section_header,
)

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


def render_dividend_focus_block(
    rows: List[PortfolioDetailRow],
    *,
    month_paid: Optional["CurrentMonthPaidDividends"] = None,
) -> None:
    """Top-of-page strip highlighting dividend income metrics investors care about most."""
    if not rows and month_paid is None:
        return

    total_annual = sum(row.annual_income or 0.0 for row in rows)
    total_value = sum(row.current_value or 0.0 for row in rows)
    portfolio_yield = (total_annual / total_value * 100) if total_value > 0 and total_annual > 0 else None

    open_dividend_focus_panel()
    render_section_header(
        "Dividend income at a glance",
        "Yield, cash flow, and upcoming payouts — the metrics dividend investors watch first.",
    )

    metrics: list[tuple[str, str, str, bool]] = []
    if month_paid is not None:
        net = (
            f" · net ${month_paid.net_usd:,.2f} est."
            if month_paid.net_usd is not None and month_paid.gross_usd > 0
            else ""
        )
        metrics.append(
            (
                f"Received ({month_paid.month_label.split()[0]})",
                f"${month_paid.gross_usd:,.2f}",
                f"{month_paid.through_label}{net}",
                True,
            )
        )
    metrics.extend(
        [
            (
                "Est. annual income",
                f"${total_annual:,.2f}" if total_annual else "—",
                "Per share × shares held",
                True,
            ),
            (
                "Est. monthly average",
                f"${total_annual / 12:,.2f}" if total_annual else "—",
                "Run-rate ÷ 12",
                True,
            ),
            (
                "Portfolio yield",
                f"{portfolio_yield:.2f}%" if portfolio_yield is not None else "—",
                "Income ÷ portfolio value",
                True,
            ),
        ]
    )
    render_metric_grid(metrics)

    ranked = sorted(rows, key=lambda row: row.annual_income or 0.0, reverse=True)
    if ranked and any(row.annual_income for row in ranked):
        st.caption(
            "**Top income:** "
            + " · ".join(
                f"**{row.ticker}** ${row.annual_income:,.0f}/yr"
                + (
                    f" ({row.dividend_yield_pct:.1f}% yield)"
                    if getattr(row, "dividend_yield_pct", None) is not None
                    else ""
                )
                for row in ranked[:5]
                if row.annual_income
            )
        )
    close_dividend_focus_panel()


def render_holdings_summary(
    rows: List[PortfolioDetailRow],
    *,
    summary: Optional[HoldingsSummary] = None,
    show_positions: bool = False,
    month_paid: Optional["CurrentMonthPaidDividends"] = None,
    show_month_received: bool = False,
) -> HoldingsSummary:
    """Render broker-style holdings summary metrics (price / P&L focus)."""
    open_panel()
    render_section_header("Portfolio snapshot", "Live value, day change, and unrealized gain/loss.")
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
                f"on or before {received.through_date.strftime('%d %b %Y')}."
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

    close_panel()
    return metrics


def render_portfolio_dividend_income_strip(rows: List[PortfolioDetailRow]) -> None:
    """Legacy wrapper — dividend focus block is preferred on Home."""
    render_dividend_focus_block(rows)
