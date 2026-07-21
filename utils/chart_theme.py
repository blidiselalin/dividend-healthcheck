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
    "income": "#2e7d32",  # dividend income / net cash — green
    "deposit": "#1565c0",  # capital deposits — blue
    "portfolio": "#2e7d32",  # portfolio value line — green
    "benchmark": "#6a1b9a",  # benchmark series — purple
    "warning": "#ef6c00",  # MoM change / caution — orange
}

# Weiss yield zones (low → high yield / cheap → expensive price)
YIELD_ZONE_COLORS: dict[str, str] = {
    "Deep Value": "#34d399",
    "Value": "#4ade80",
    "Fair Value": "#fbbf24",
    "Caution": "#fb923c",
    "Expensive": "#f87171",
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
    palette = chart_palette()
    from ui.theme_mode import THEME_LIGHT, get_theme_mode

    is_light = get_theme_mode() == THEME_LIGHT
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
        "template": "plotly_white" if is_light else "plotly_dark",
        "autosize": True,
        "font": {
            "family": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            "size": 12,
            "color": palette["text"],
        },
        "paper_bgcolor": palette["paper"],
        "plot_bgcolor": palette["plot"],
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": palette["paper"],
            "bordercolor": palette["border"],
            "font_size": 12,
            "font_color": palette["text"],
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
            "font": {"size": 15, "color": palette["text"], "weight": "bold"},
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
            "bgcolor": palette["plot"],
            "bordercolor": palette["grid"],
            "borderwidth": 1,
        }

    fig.update_layout(**layout)
    fig.update_xaxes(
        showgrid=True,
        gridcolor=palette["grid"],
        linecolor=palette["grid"],
        tickfont={"size": 11, "color": palette["muted"]},
        title_font={"size": 12, "color": palette["muted"]},
        automargin=True,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=palette["grid"],
        linecolor=palette["grid"],
        tickfont={"size": 11, "color": palette["muted"]},
        title_font={"size": 12, "color": palette["muted"]},
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


DARK_PALETTE: dict[str, str] = {
    "paper": "#131c2e",
    "plot": "#0f172a",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "grid": "rgba(148, 163, 184, 0.14)",
    "border": "rgba(42, 58, 82, 0.9)",
    "primary": "#2dd4bf",
    "yield_line": "#fbbf24",
    "yield_fill": "rgba(251, 191, 36, 0.14)",
}

LIGHT_PALETTE: dict[str, str] = {
    "paper": "#ffffff",
    "plot": "#f8fafc",
    "text": "#0f172a",
    "muted": "#64748b",
    "grid": "rgba(148, 163, 184, 0.35)",
    "border": "rgba(203, 213, 225, 0.9)",
    "primary": "#0f766e",
    "yield_line": "#d97706",
    "yield_fill": "rgba(217, 119, 6, 0.12)",
}


def chart_palette() -> dict[str, str]:
    try:
        from ui.theme_mode import THEME_LIGHT, get_theme_mode

        return LIGHT_PALETTE if get_theme_mode() == THEME_LIGHT else DARK_PALETTE
    except Exception:
        return DARK_PALETTE


def hex_rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"


def yield_zone_fill(zone_name: str, *, alpha: float = 0.16) -> str:
    return hex_rgba(YIELD_ZONE_COLORS[zone_name], alpha)


def style_yield_channel_figure(fig: Any, *, height: int = 480) -> Any:
    """Dashboard styling for the Dividends Don't Lie yield channel chart."""
    palette = chart_palette()
    from ui.theme_mode import THEME_LIGHT, get_theme_mode

    is_light = get_theme_mode() == THEME_LIGHT
    fig.update_layout(
        height=height,
        autosize=True,
        template="plotly_white" if is_light else "plotly_dark",
        font={
            "family": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            "size": 12,
            "color": palette["text"],
        },
        paper_bgcolor=palette["paper"],
        plot_bgcolor=palette["plot"],
        hovermode="x unified",
        hoverlabel={
            "bgcolor": palette["paper"],
            "bordercolor": palette["border"],
            "font_size": 12,
            "font_color": palette["text"],
            "namelength": -1,
        },
        margin={"l": 58, "r": 42, "t": 64, "b": 44},
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.03,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 10, "color": palette["muted"]},
            "bgcolor": palette["plot"],
            "bordercolor": palette["border"],
            "borderwidth": 1,
        },
    )
    fig.update_annotations(
        font={
            "size": 12,
            "color": palette["muted"],
            "family": "system-ui, sans-serif",
        },
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=palette["grid"],
        linecolor=palette["grid"],
        tickfont={"size": 11, "color": palette["muted"]},
        zeroline=False,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=palette["grid"],
        linecolor=palette["grid"],
        tickfont={"size": 11, "color": palette["muted"]},
        title_font={"size": 12, "color": palette["muted"]},
        zeroline=False,
    )
    return fig


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
