"""
Compact portfolio positions table for the home view.

Worst performers first; click a row (ticker) to open full holding analysis.
Plain dataframe + row selection avoids the styled-grid overlay-editor JS chunk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from services.portfolio_details_service import PortfolioDetailRow

from services.portfolio_holdings_summary import sort_positions_worst_first
from services.portfolio_position_table import (
    build_home_positions_dataframe,
    risk_hints_by_ticker,
    style_home_positions_dataframe,
)
from ui.design_system import close_table_container, render_section_header, wrap_table_container


def _load_risk_hints() -> dict[str, str]:
    try:
        from ui.portfolio_risk_panel import get_cached_attention_summary

        summary = get_cached_attention_summary()
        if summary is None:
            return {}
        return risk_hints_by_ticker(getattr(summary, "risk_items", None))
    except Exception:
        return {}


def render_positions_table(
    rows: list[PortfolioDetailRow],
    *,
    table_key: str = "home_positions_table",
) -> None:
    """Interactive positions table — row click opens dividend analysis."""
    if not rows:
        return

    from ui.portfolio_home import set_holding_selection

    sorted_rows = sort_positions_worst_first(rows)
    nav_tickers = [row.ticker for row in sorted_rows]
    df = build_home_positions_dataframe(sorted_rows, risk_hints=_load_risk_hints())
    styled_df = style_home_positions_dataframe(df)

    render_section_header(
        "All positions",
        "Worst performers first · click a row to open dividend analysis. "
        "Red = loss · green = gain.",
    )
    wrap_table_container()

    selection = st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=table_key,
        column_config={
            "Ticker": st.column_config.TextColumn(
                width="small",
                help="Click the row to open full analysis for this holding.",
            ),
            "Company": st.column_config.TextColumn(width="medium"),
            "Concerns": st.column_config.TextColumn(
                width="large",
                help="Data quality, performance, yield, and risk flags to review.",
            ),
            "Status": st.column_config.TextColumn(
                width="small",
                help="⏳ stale price · 📉 thin history · ✓ OK",
            ),
            "P/L %": st.column_config.NumberColumn(
                format="%+.1f%%",
                help="Unrealized gain/loss on cost basis.",
            ),
            "P/L": st.column_config.ProgressColumn(
                format="%.0f",
                min_value=0,
                max_value=100,
                help="Visual P/L: bar left of center = loss (red), right = gain (green).",
            ),
            "Day %": st.column_config.NumberColumn(
                format="%+.2f%%",
                help="Today's price change vs previous close.",
            ),
            "1Y %": st.column_config.NumberColumn(
                format="%+.1f%%",
                help="Price change vs ~12 months ago.",
            ),
            "Yield %": st.column_config.NumberColumn(format="%.2f%%"),
            "Weight %": st.column_config.NumberColumn(format="%.1f%%"),
            "Value $": st.column_config.NumberColumn(format="$%.0f"),
            "Sector": st.column_config.TextColumn(width="small"),
        },
    )
    close_table_container()

    selected_rows = getattr(getattr(selection, "selection", None), "rows", None)
    if selected_rows:
        ticker = df.iloc[selected_rows[0]]["Ticker"]
        set_holding_selection(str(ticker), nav_tickers=nav_tickers)
