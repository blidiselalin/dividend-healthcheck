"""Holdings summary strip — total value, day change, unrealized P/L."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import streamlit as st

from services.portfolio_details_service import PortfolioDetailRow, PortfolioDetailsService
from services.portfolio_holdings_summary import HoldingsSummary, compute_holdings_summary
from ui.design_system import (
    render_dividend_focus_panel,
    render_home_panel,
)

if TYPE_CHECKING:
    from services.portfolio_month_dividends import CurrentMonthPaidDividends


def _format_delta(value: float | None, pct: float | None) -> str:
    if value is None:
        return "Reload live data for today's move"
    if pct is not None:
        return f"{pct:+.2f}%"
    return f"${value:+,.2f}"


@dataclass(frozen=True)
class PortfolioHealthSnapshot:
    """Compact health figures already computed on portfolio rows."""

    sectors: tuple[tuple[str, float], ...]
    largest_positions: tuple[tuple[str, float], ...]
    income_leaders: tuple[tuple[str, float], ...]
    unpriced: tuple[str, ...]
    stale_prices: tuple[str, ...]


def _top_weights(
    rows: list[PortfolioDetailRow],
    attr: str,
    *,
    limit: int = 3,
) -> tuple[tuple[str, float], ...]:
    ranked: list[tuple[str, float]] = []
    for row in rows:
        weight = getattr(row, attr, None)
        if weight is None or weight <= 0:
            continue
        ranked.append((row.ticker, float(weight)))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return tuple(ranked[:limit])


def build_portfolio_health(rows: list[PortfolioDetailRow]) -> PortfolioHealthSnapshot:
    """Sector weights, concentration, and missing prices. No new valuation math."""
    from services.portfolio_allocation_service import (
        PortfolioAllocationService,
        unpriced_tickers,
    )

    sectors: list[tuple[str, float]] = []
    frame = PortfolioAllocationService().sector_allocation(rows)
    if not frame.empty:
        for record in frame.head(6).itertuples(index=False):
            sectors.append((str(record[0]), float(record[2])))
    stale = tuple(row.ticker for row in rows if row.price_stale)
    return PortfolioHealthSnapshot(
        sectors=tuple(sectors),
        largest_positions=_top_weights(rows, "weight_pct"),
        income_leaders=_top_weights(rows, "income_weight_pct"),
        unpriced=tuple(unpriced_tickers(rows)),
        stale_prices=stale,
    )


def render_portfolio_health(rows: list[PortfolioDetailRow]) -> None:
    """Sector exposure and concentration on Home. Full charts stay on Holdings."""
    if not rows:
        return
    health = build_portfolio_health(rows)
    st.markdown("##### Portfolio health")
    st.caption(
        "Sector weights use current market value. "
        "A holding with no price is excluded. "
        "Income share is the projected annual income already on each holding."
    )
    if health.sectors:
        left, right = st.columns(2)
        with left:
            st.caption("Sector exposure")
            for name, weight in health.sectors:
                st.write(f"{name} · {weight:.1f}%")
        with right:
            st.caption("Largest positions")
            if health.largest_positions:
                for ticker, weight in health.largest_positions:
                    st.write(f"{ticker} · {weight:.1f}% of value")
            else:
                st.write("Position weights appear after prices load.")
            st.caption("Projected income concentration")
            if health.income_leaders:
                for ticker, weight in health.income_leaders:
                    st.write(f"{ticker} · {weight:.1f}% of projected income")
            else:
                st.write("No projected income on these holdings.")
    notices: list[str] = []
    if health.unpriced:
        notices.append("No price: " + ", ".join(health.unpriced))
    if health.stale_prices:
        notices.append("Stale price: " + ", ".join(health.stale_prices))
    if notices:
        st.caption(" · ".join(notices))


def render_dividend_focus_block(
    rows: list[PortfolioDetailRow],
    *,
    month_paid: CurrentMonthPaidDividends | None = None,
) -> None:
    """Top-of-page strip highlighting dividend income metrics investors care about most."""
    if not rows and month_paid is None:
        return

    total_annual = sum(row.annual_income or 0.0 for row in rows)
    total_value = sum(row.current_value or 0.0 for row in rows)
    portfolio_yield = (
        (total_annual / total_value * 100) if total_value > 0 and total_annual > 0 else None
    )

    metrics: list[tuple[str, str, str, bool]] = []
    if month_paid is not None:
        net = ""
        if month_paid.net_usd is not None and month_paid.gross_usd > 0:
            estimate = " est." if month_paid.net_is_estimate else ""
            net = f" · net ${month_paid.net_usd:,.2f}{estimate}"
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
    render_dividend_focus_panel(
        "Dividend income at a glance",
        "Yield, cash flow, and upcoming payouts — the metrics dividend investors watch first.",
        metrics,
    )

    ranked = sorted(rows, key=lambda row: row.annual_income or 0.0, reverse=True)
    chips = [
        (
            row.ticker,
            f"${row.annual_income:,.0f}/yr"
            + (
                f" · {row.dividend_yield_pct:.1f}%"
                if getattr(row, "dividend_yield_pct", None) is not None
                else ""
            ),
        )
        for row in ranked[:5]
        if row.annual_income
    ]
    if chips:
        st.caption("Top income contributors — click to open analysis")
        nav = [symbol for symbol, _detail in chips]
        cols = st.columns(min(len(chips), 5))
        for index, (symbol, detail) in enumerate(chips):
            with cols[index]:
                if st.button(
                    f"{symbol} · {detail}",
                    key=f"home_income_chip_{symbol}",
                    use_container_width=True,
                ):
                    from ui.portfolio_home import set_holding_selection

                    set_holding_selection(symbol, nav_tickers=nav)


def render_holdings_summary(
    rows: list[PortfolioDetailRow],
    *,
    summary: HoldingsSummary | None = None,
    show_positions: bool = False,
    month_paid: CurrentMonthPaidDividends | None = None,
    show_month_received: bool = False,
) -> HoldingsSummary:
    """Render broker-style holdings summary metrics (price / P&L focus)."""
    if summary is None and rows and any(row.previous_close is None for row in rows):
        rows = PortfolioDetailsService().enrich_rows_previous_close(rows)
        with contextlib.suppress(Exception):
            st.session_state["portfolio_details_rows"] = rows

    metrics = summary or compute_holdings_summary(rows)
    include_received = show_month_received and month_paid is not None

    cards: list[tuple[str, str, str, bool]] = []
    if show_positions:
        cards.append(("Positions", str(metrics.positions), "Open holdings", False))

    cards.append(
        (
            "Total value",
            f"${metrics.total_value_usd:,.2f}",
            "Open equity × live/library price (cash excluded)",
            True,
        )
    )

    if include_received and month_paid is not None:
        net_hint = ""
        if month_paid.net_usd is not None and month_paid.gross_usd > 0:
            estimate = " est." if month_paid.net_is_estimate else ""
            net_hint = f" · net ${month_paid.net_usd:,.2f}{estimate}"
        cards.append(
            (
                f"Received ({month_paid.month_label.split()[0]})",
                f"${month_paid.gross_usd:,.2f}",
                f"{month_paid.through_label}{net_hint}",
                True,
            )
        )

    cards.append(
        (
            "Day change",
            (f"${metrics.day_change_usd:+,.2f}" if metrics.day_change_usd is not None else "—"),
            _format_delta(metrics.day_change_usd, metrics.day_change_pct),
            True,
        )
    )
    cards.append(
        (
            "Unrealized G/L",
            f"${metrics.unrealized_gl_usd:+,.2f}",
            _format_delta(metrics.unrealized_gl_usd, metrics.unrealized_gl_pct),
            True,
        )
    )

    render_home_panel(
        "Portfolio snapshot",
        "Market value and unrealized performance for open positions.",
        cards,
    )
    return metrics
