"""
Shared Plotly styling for DividendScope — clean, consistent charts app-wide.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Match portfolio UI (teal) and readable neutrals
PALETTE: Dict[str, str] = {
    "primary": "#0f766e",
    "primary_light": "#14b8a6",
    "accent": "#c2410c",
    "text": "#0f172a",
    "muted": "#64748b",
    "grid": "rgba(148, 163, 184, 0.22)",
    "plot_bg": "#f8fafc",
    "paper": "#ffffff",
}

# Weiss yield zones (low → high yield / cheap → expensive price)
YIELD_ZONE_COLORS: Dict[str, str] = {
    "Deep Value": "#166534",
    "Value": "#16a34a",
    "Fair Value": "#ca8a04",
    "Caution": "#ea580c",
    "Expensive": "#dc2626",
}

CATEGORICAL: tuple = (
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
    title: Optional[str] = None,
    height: Optional[int] = None,
    legend: bool = True,
    horizontal_legend: bool = False,
    margin: Optional[Dict[str, int]] = None,
) -> Any:
    """Apply DividendScope defaults without removing trace-specific layout."""
    top = 56 if title else 36
    default_margin = dict(l=52, r=28, t=top, b=44)
    if margin:
        default_margin.update(margin)
    else:
        existing = fig.layout.margin
        if existing is not None:
            for edge in ("l", "r", "t", "b"):
                value = getattr(existing, edge, None)
                if value is not None and value > default_margin[edge]:
                    default_margin[edge] = value

    layout: Dict[str, Any] = dict(
        template="plotly_white",
        font=dict(
            family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            size=12,
            color=PALETTE["text"],
        ),
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["plot_bg"],
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", font_size=12, font_color=PALETTE["text"]),
        margin=default_margin,
        showlegend=legend,
    )
    if height is not None:
        layout["height"] = height
    if title:
        layout["title"] = dict(
            text=title,
            x=0,
            xanchor="left",
            font=dict(size=14, color=PALETTE["text"]),
        )
    if horizontal_legend and legend:
        layout["legend"] = dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=10),
            bgcolor="rgba(255,255,255,0.85)",
        )

    fig.update_layout(**layout)
    fig.update_xaxes(
        showgrid=True,
        gridcolor=PALETTE["grid"],
        linecolor=PALETTE["grid"],
        tickfont=dict(size=11, color=PALETTE["muted"]),
        title_font=dict(size=12, color=PALETTE["muted"]),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=PALETTE["grid"],
        linecolor=PALETTE["grid"],
        tickfont=dict(size=11, color=PALETTE["muted"]),
        title_font=dict(size=12, color=PALETTE["muted"]),
    )
    return fig


def monthly_category_axis(category_count: int) -> Dict[str, Any]:
    """X-axis settings for month labels — reduces tick overlap on long histories."""
    if category_count <= 8:
        return dict(tickangle=0, automargin=True)
    if category_count <= 14:
        return dict(tickangle=-35, nticks=min(category_count, 12), automargin=True)
    return dict(
        tickangle=-55,
        nticks=min(category_count, 14),
        tickfont=dict(size=10),
        automargin=True,
    )


def evolution_chart_margins(category_count: int) -> Dict[str, int]:
    """Bottom margin sized for rotated month labels."""
    if category_count <= 8:
        bottom = 72
    elif category_count <= 14:
        bottom = 100
    else:
        bottom = 130
    return dict(t=48, b=bottom, l=56, r=32)


def style_subplot_titles(fig: Any, *, size: int = 13, color: Optional[str] = None) -> Any:
    """Normalize subplot title typography."""
    color = color or PALETTE["text"]
    fig.update_annotations(
        font=dict(size=size, color=color, family="system-ui, sans-serif"),
    )
    return fig
