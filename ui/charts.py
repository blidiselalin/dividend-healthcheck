"""
Streamlit helpers for Plotly charts (uses utils.chart_theme).
"""

from __future__ import annotations

from typing import Any

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
    key: str | None = None,
    height: int | None = None,
    title: str | None = None,
    subtitle: str | None = None,
    **kwargs: Any,
) -> Any:
    """Render a styled Plotly figure full width (passes through Streamlit plotly_chart kwargs)."""
    if fig is None:
        from ui.design_system import render_empty_state

        render_empty_state(
            "No chart data", "Reload live data or check the shared library.", icon="📉"
        )
        return None
    if title:
        from ui.design_system import render_chart_card_header

        render_chart_card_header(title, subtitle or "")
    if height is not None and fig.layout.height is None:
        fig.update_layout(height=height)
    result = st.plotly_chart(
        fig,
        width=kwargs.pop("width", "stretch"),
        key=key,
        config=PLOTLY_CONFIG,
        **kwargs,
    )
    if title:
        from ui.design_system import render_chart_card_footer

        render_chart_card_footer()
    return result


__all__ = ["show_chart", "style_figure", "PLOTLY_CONFIG"]
