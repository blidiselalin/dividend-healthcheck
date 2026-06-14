"""Shared Streamlit-cached helpers for market library admin views."""

from __future__ import annotations

import streamlit as st


@st.cache_data(ttl=120, show_spinner=False)
def cached_thin_history_summary() -> dict:
    from services.stock_history_backfill import thin_history_summary

    return thin_history_summary()


def clear_thin_history_summary_cache() -> None:
    cached_thin_history_summary.clear()
