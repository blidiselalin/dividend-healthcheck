"""
Shared Plotly styling for DividendScope — clean, consistent charts app-wide.
"""

from __future__ import annotations

from typing import Any

# Match portfolio UI (teal) and readable neutrals
PALETTE: dict[str, str] = {
    "primary": "#0f766e",
    "primary_light": "#14b8a6",
    "accent": "#c2410c",
    "text": "#0f172a",
    "muted": "#64748b",
    "grid": "rgba(148, 163, 184, 0.22)",
    "plot_bg": "#f8fafc",
    "paper": "#ffffff",
    # Semantic aliases used across chart services
    "income": "#2e7d32",       # dividend income / net cash — green
    "deposit": "#1565c0",      # capital deposits — blue
    "portfolio": "#2e7d32",    # portfolio value line — green
    "benchmark": "#6a1b9a",    # benchmark series — purple
    "warning": "#ef6c00",      # MoM change / caution — orange
}

# Weiss yield zones (low → high yield / cheap → expensive price)
YIELD_ZONE_COLORS: dict[str, str] = {
    "Deep Value": "#166534",
    "Value": "#16a34a",
    "Fair Value": "#ca8a04",
    "Caution": "#ea580c",
    "Expensive": "#dc2626",
}

# Ordered palette for categorical series (bar groups, line charts)
CATEGORICAL: tuple[str, ...] = (
    "#0f766e",
    "#0369a1",
    "#7c3aed",
    "#c2410c",
    "#b45309",
    "#64748b",
)


def style_figure(
    fig: Any,
    *,
    title: str | None = None,
    height: int | None = None,
    legend: bool = True,
    horizontal_legend: bool = False,
    margin: dict[str, int] | None = None,
) -> Any:
    """Apply DividendScope defaults without removing trace-specific layout."""
    top = 60 if title else 36
    default_margin = {"l": 52, "r": 28, "t": top, "b": 44}
    if margin:
        default_margin.update(margin)
    else:
        existing = fig.layout.margin
        if existing is not None:
            for edge in ("l", "r", "t", "b"):
                value = getattr(existing, edge, None)
                if value is not None and value > default_margin[edge]:
                    default_margin[edge] = value

    layout: dict[str, Any] = {
        "template": "plotly_white",
        "autosize": True,
        "font": {
            "family": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            "size": 12,
            "color": PALETTE["text"],
        },
        "paper_bgcolor": PALETTE["paper"],
        "plot_bgcolor": PALETTE["plot_bg"],
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": "white",
            "bordercolor": PALETTE["grid"],
            "font_size": 12,
            "font_color": PALETTE["text"],
            "namelength": -1,
        },
        "margin": default_margin,
        "showlegend": legend,
    }
    if height is not None:
        layout["height"] = height
    if title:
        layout["title"] = {
            "text": title,
            "x": 0,
            "xanchor": "left",
            "font": {"size": 15, "color": PALETTE["text"], "weight": "bold"},
            "pad": {"b": 8},
        }
    if horizontal_legend and legend:
        layout["legend"] = {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
            "bgcolor": "rgba(255,255,255,0.85)",
            "bordercolor": PALETTE["grid"],
            "borderwidth": 1,
        }

    fig.update_layout(**layout)
    fig.update_xaxes(
        showgrid=True,
        gridcolor=PALETTE["grid"],
        linecolor=PALETTE["grid"],
        tickfont={"size": 11, "color": PALETTE["muted"]},
        title_font={"size": 12, "color": PALETTE["muted"]},
        automargin=True,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=PALETTE["grid"],
        linecolor=PALETTE["grid"],
        tickfont={"size": 11, "color": PALETTE["muted"]},
        title_font={"size": 12, "color": PALETTE["muted"]},
        automargin=True,
    )
    return fig


def monthly_category_axis(category_count: int) -> dict[str, Any]:
    """X-axis settings for month labels — reduces tick overlap on long histories."""
    if category_count <= 6:
        return {"tickangle": 0, "automargin": True}
    if category_count <= 12:
        return {"tickangle": -35, "nticks": min(category_count, 10), "automargin": True}
    return {
        "tickangle": -55,
        "nticks": min(category_count, 12),
        "tickfont": {"size": 9},
        "automargin": True,
    }


def evolution_chart_margins(
    category_count: int,
    *,
    legend_bottom: bool = False,
    dual_y: bool = False,
) -> dict[str, int]:
    """Margins sized for month labels and optional bottom legend (no in-chart title)."""
    if category_count <= 6:
        bottom = 64
    elif category_count <= 12:
        bottom = 96
    else:
        bottom = 128
    if legend_bottom:
        bottom += 40
    return {
        "t": 40,
        "b": bottom,
        "l": 56,
        "r": 52 if dual_y else 32,
    }


def bottom_legend() -> dict[str, Any]:
    """Horizontal legend below the plot — avoids overlapping Streamlit section titles."""
    return {
        "orientation": "h",
        "yanchor": "top",
        "y": -0.22,
        "x": 0.5,
        "xanchor": "center",
        "font": {"size": 11},
        "bgcolor": "rgba(255,255,255,0.92)",
        "bordercolor": "rgba(148, 163, 184, 0.3)",
        "borderwidth": 1,
    }


def outside_bar_text() -> dict[str, Any]:
    """Trace-level kwargs for bars with outside text labels (prevents clipping)."""
    return {
        "textposition": "outside",
        "cliponaxis": False,
        "textfont": {"size": 11},
    }


def style_subplot_titles(fig: Any, *, size: int = 13, color: str | None = None) -> Any:
    """Normalize subplot title typography."""
    color = color or PALETTE["text"]
    fig.update_annotations(
        font={"size": size, "color": color, "family": "system-ui, sans-serif"},
    )
    return fig
