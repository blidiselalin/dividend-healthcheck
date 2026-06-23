"""
Compact portfolio positions table for the home view.

Worst performers appear first; selecting a row opens full holding analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

if TYPE_CHECKING:
    from services.portfolio_details_service import PortfolioDetailRow

from services.portfolio_holdings_summary import sort_positions_worst_first

_COMPANY_MAX_LEN = 32


def build_positions_table_df(rows: list[PortfolioDetailRow]) -> pd.DataFrame:
    """Key figures only — readable at a glance on the home screen."""
    records = []
    for row in rows:
        company = row.company or row.ticker
        if len(company) > _COMPANY_MAX_LEN:
            company = company[: _COMPANY_MAX_LEN - 1].rstrip() + "…"
        records.append(
            {
                "Ticker": row.ticker,
                "Company": company,
                "Value $": row.current_value,
                "Weight %": row.weight_pct,
                "P/L %": row.profit_pct,
                "P/L $": row.profit,
                "Yield %": row.dividend_yield_pct,
                "Income/yr $": row.annual_income,
                "Price $": row.current_price,
            }
        )
    return pd.DataFrame(records)


def style_positions_table(df: pd.DataFrame) -> pd.DataFrame | object:
    """Highlight P/L % so weak positions stand out."""

    def _profit_style(value: object) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        try:
            pct = float(value)
        except (TypeError, ValueError):
            return ""
        if pct <= -15:
            return "background-color: #ffebee; color: #b71c1c; font-weight: 600"
        if pct < 0:
            return "background-color: #fff3e0; color: #bf360c; font-weight: 600"
        if pct >= 25:
            return "background-color: #e8f5e9; color: #1b5e20"
        return ""

    if df.empty:
        return df
    return df.style.map(_profit_style, subset=["P/L %"])


def render_positions_table(
    rows: list[PortfolioDetailRow],
    *,
    table_key: str = "home_positions_table",
) -> None:
    """Render sortable positions table; row selection opens holding analysis."""
    if not rows:
        return

    from ui.portfolio_home import set_holding_selection

    sorted_rows = sort_positions_worst_first(rows)
    nav_tickers = [row.ticker for row in sorted_rows]
    df = build_positions_table_df(sorted_rows)
    display_df = style_positions_table(df)

    st.markdown("#### All positions")
    st.caption(
        "Worst performers first · select a row to open dividend analysis for that ticker."
    )

    selection = st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=table_key,
        column_config={
            "Ticker": st.column_config.TextColumn(
                width="small",
                help="Select the row to open full analysis.",
            ),
            "Company": st.column_config.TextColumn(width="medium"),
            "Value $": st.column_config.NumberColumn(format="$%.0f"),
            "Weight %": st.column_config.NumberColumn(format="%.1f%%"),
            "P/L %": st.column_config.NumberColumn(format="%+.1f%%"),
            "P/L $": st.column_config.NumberColumn(format="$%+.0f"),
            "Yield %": st.column_config.NumberColumn(format="%.2f%%"),
            "Income/yr $": st.column_config.NumberColumn(format="$%.0f"),
            "Price $": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    selected_rows = getattr(getattr(selection, "selection", None), "rows", None)
    if selected_rows:
        ticker = df.iloc[selected_rows[0]]["Ticker"]
        set_holding_selection(ticker, nav_tickers=nav_tickers)
