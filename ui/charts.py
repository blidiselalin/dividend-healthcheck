"""
Streamlit helpers for Plotly charts (uses utils.chart_theme).
"""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from utils.chart_theme import style_figure

# Clean toolbar: zoom/pan/download only — no Plotly branding
PLOTLY_CONFIG: dict = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
        "autoScale2d",
    ],
}


def show_chart(
    fig: Any,
    *,
    key: Optional[str] = None,
    height: Optional[int] = None,
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


__all__ = ["show_chart", "style_figure", "PLOTLY_CONFIG"]
