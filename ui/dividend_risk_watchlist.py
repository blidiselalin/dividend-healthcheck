"""
Home Dividend Risk Watchlist — payout / FCF / safety flags for open holdings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

from services.dividend_health import HEALTH_RISKY, HEALTH_WATCH
from services.dividend_risk_watchlist import (
    build_dividend_risk_watchlist,
    watchlist_counts,
    watchlist_to_records,
)
from services.dividend_terminology import term_help
from ui.design_system import (
    close_table_container,
    render_home_panel,
    wrap_table_container,
)
from ui.user_guidance import render_actionable_empty_state

if TYPE_CHECKING:
    from services.portfolio_details_service import PortfolioDetailRow


def _stock_cache() -> dict:
    return dict(st.session_state.get("portfolio_stock_cache") or {})


def render_dividend_risk_watchlist(
    rows: list[PortfolioDetailRow],
    *,
    table_key: str = "home_dividend_risk_watchlist",
) -> None:
    """Prominent Home card: Watch / Risky dividend sustainability flags."""
    if not rows:
        return

    from ui.portfolio_home import set_holding_selection

    items = build_dividend_risk_watchlist(rows, _stock_cache())
    counts = watchlist_counts(items)

    render_home_panel(
        "Dividend risk watchlist",
        "Watch / Risky names by payout, FCF coverage, and safety score. "
        "Click a row for full analysis — research only, not advice.",
        [
            ("On watchlist", str(counts["total"]), "Flagged holdings", True),
            ("Risky", str(counts["risky"]), "Needs attention", True),
            ("Watch", str(counts["watch"]), "Monitor closely", True),
        ],
    )

    if not items:
        render_actionable_empty_state(
            title="No dividend risks flagged",
            description=(
                "Current holdings look Healthy on available payout and safety data. "
                "Open Holdings to review yields and upcoming payments."
            ),
            icon="✅",
            primary_action_label="Review holdings",
            primary_action_route="holdings",
            secondary_action_label="Dividend terms",
            secondary_action_route="help:dividends",
            key_prefix="empty_div_risk_watch",
        )
        return

    df = pd.DataFrame(watchlist_to_records(items))
    wrap_table_container()
    selection = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=table_key,
        column_config={
            "Ticker": st.column_config.TextColumn(width="small"),
            "Company": st.column_config.TextColumn(width="medium"),
            "Yield %": st.column_config.NumberColumn(
                format="%.2f%%",
                help=term_help("dividend_yield"),
            ),
            "Payout %": st.column_config.NumberColumn(
                format="%.0f%%",
                help="Share of earnings paid as dividends. High payouts leave less buffer.",
            ),
            "FCF payout %": st.column_config.NumberColumn(
                format="%.0f%%",
                help="Dividends as a % of free cash flow. Above 100% is a stress signal.",
            ),
            "FCF coverage": st.column_config.NumberColumn(
                format="%.2f×",
                help="Free cash flow ÷ dividend. Below 1.0× means FCF does not cover the dividend.",
            ),
            "Safety score": st.column_config.NumberColumn(
                format="%.0f",
                help="0–100 score from payout and FCF payout (higher is safer).",
            ),
            "Safety": st.column_config.TextColumn(
                width="small",
                help=f"{HEALTH_RISKY} needs attention · {HEALTH_WATCH} monitor · Healthy omitted here.",
            ),
            "Why": st.column_config.TextColumn(width="large"),
        },
    )
    close_table_container()

    selected_rows = getattr(getattr(selection, "selection", None), "rows", None) or []
    if selected_rows:
        index = int(selected_rows[0])
        if 0 <= index < len(items):
            set_holding_selection(
                items[index].ticker,
                nav_tickers=[item.ticker for item in items],
            )
