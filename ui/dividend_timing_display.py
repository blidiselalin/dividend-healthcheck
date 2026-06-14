"""Styled tables for dividend timing (upcoming vs paid)."""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from services.dividend_timing import style_dividend_timing_dataframe


def render_dividend_timing_dataframe(
    df: Any,
    *,
    table_key: str,
    on_select: bool = True,
) -> Any:
    """Show a dividend table with row colors by timing (no severity column)."""
    if df is None or df.empty:
        return None

    styled = style_dividend_timing_dataframe(df)
    column_config = {}
    if "Ex-Date" in df.columns:
        column_config["Ex-Date"] = st.column_config.DateColumn(format="YYYY-MM-DD")
    if "Pay Date" in df.columns:
        column_config["Pay Date"] = st.column_config.DateColumn(format="YYYY-MM-DD")
    if "Per Share" in df.columns:
        column_config["Per Share"] = st.column_config.NumberColumn(format="$%.4f")
    if "Shares" in df.columns:
        column_config["Shares"] = st.column_config.NumberColumn(format="%.0f")
    if "Expected Cash" in df.columns:
        column_config["Expected Cash"] = st.column_config.NumberColumn(format="$%.2f")
    if "Received" in df.columns:
        column_config["Received"] = st.column_config.NumberColumn(format="$%.2f")

    kwargs = {
        "width": "stretch",
        "hide_index": True,
        "key": table_key,
    }
    if column_config:
        kwargs["column_config"] = column_config

    if on_select:
        kwargs["on_select"] = "rerun"
        kwargs["selection_mode"] = "single-row"

    return st.dataframe(styled, **kwargs)


def dividend_timing_legend() -> None:
    st.caption(
        "Row colors: **blue** = upcoming ex-date · **amber** = ex-date passed, payment soon · "
        "**green** = upcoming payment · **gray** = already paid · **purple** = projected estimate."
    )
