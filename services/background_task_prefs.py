"""
User preferences for automatic background portfolio and market-library tasks.

Background enrichment is **off by default** so the UI can paint quickly from disk
cache. Users enable automatic tasks or run individual jobs from the sidebar panel.
"""

from __future__ import annotations

AUTO_BACKGROUND_TASKS_KEY = "background_tasks_auto_enabled"


def _session_state() -> dict:
    try:
        import streamlit as st

        return st.session_state
    except Exception:  # noqa: BLE001
        return {}


def auto_background_tasks_enabled() -> bool:
    """True when the user opted in to automatic background tasks on load."""
    return bool(_session_state().get(AUTO_BACKGROUND_TASKS_KEY))


def set_auto_background_tasks_enabled(enabled: bool) -> None:
    _session_state()[AUTO_BACKGROUND_TASKS_KEY] = enabled
