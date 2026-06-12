"""
Streamlit helpers for Plotly charts (uses utils.chart_theme).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from utils.chart_theme import style_figure

# Clean toolbar: zoom/pan/download only
PLOTLY_CONFIG: dict[str, Any] = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
        "autoScale2d",
    ],
}


def show_chart(
    fig: Any,
    *,
    key: str | None = None,
    height: int | None = None,
    **kwargs: Any,
) -> Any:
    """Render a styled Plotly figure full width (passes through Streamlit plotly_chart kwargs)."""
    if fig is None:
        return None
    if height is not None and fig.layout.height is None:
        fig.update_layout(height=height)
    return st.plotly_chart(
        fig,
        width=kwargs.pop("width", "stretch"),
        key=key,
        config=PLOTLY_CONFIG,
        **kwargs,
    )


__all__ = ["PLOTLY_CONFIG", "show_chart", "style_figure"]
