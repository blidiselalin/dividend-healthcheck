"""
Compact portfolio positions table for the home view.

Worst performers appear first; pick a ticker below to open full holding analysis.

Uses a plain ``st.dataframe`` (no pandas Styler / row selection) so production
proxies do not need Streamlit's lazy-loaded data-grid overlay editor chunk.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

if TYPE_CHECKING:
    from services.portfolio_details_service import PortfolioDetailRow

from services.portfolio_holdings_summary import sort_positions_worst_first

_COMPANY_MAX_LEN = 32


def _profit_signal(profit_pct: float | None) -> str:
    if profit_pct is None or (isinstance(profit_pct, float) and pd.isna(profit_pct)):
        return "—"
    if profit_pct <= -15:
        return "Loss"
    if profit_pct < 0:
        return "Down"
    if profit_pct >= 25:
        return "Strong"
    return "—"


def build_positions_table_df(rows: list[PortfolioDetailRow]) -> pd.DataFrame:
    """Key figures only — readable at a glance on the home screen."""
    records = []
    for row in rows:
        company = row.company or row.ticker
        if len(company) > _COMPANY_MAX_LEN:
            company = company[: _COMPANY_MAX_LEN - 1].rstrip() + "…"
        records.append(
            {
                "Signal": _profit_signal(row.profit_pct),
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


def render_positions_table(
    rows: list[PortfolioDetailRow],
    *,
    table_key: str = "home_positions_table",
) -> None:
    """Render positions table and open-analysis control (no interactive grid selection)."""
    if not rows:
        return

    from ui.portfolio_home import set_holding_selection

    sorted_rows = sort_positions_worst_first(rows)
    nav_tickers = [row.ticker for row in sorted_rows]
    df = build_positions_table_df(sorted_rows)

    st.markdown("#### All positions")
    st.caption(
        "Worst performers first · choose a ticker below to open dividend analysis."
    )

    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        key=table_key,
        column_config={
            "Signal": st.column_config.TextColumn(
                width="small",
                help="Loss / Down / Strong from unrealized P/L %.",
            ),
            "Ticker": st.column_config.TextColumn(width="small"),
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

    pick_col, action_col = st.columns([4, 1])
    with pick_col:
        selected = st.selectbox(
            "Analyze holding",
            nav_tickers,
            format_func=lambda symbol: next(
                (f"{row.ticker} — {row.company}" for row in sorted_rows if row.ticker == symbol),
                symbol,
            ),
            key=f"{table_key}_pick",
        )
    with action_col:
        st.markdown('<div style="height: 1.65rem"></div>', unsafe_allow_html=True)
        if st.button("Open →", key=f"{table_key}_open", use_container_width=True):
            set_holding_selection(selected, nav_tickers=nav_tickers)
