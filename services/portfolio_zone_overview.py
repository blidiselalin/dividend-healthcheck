"""
Portfolio-level dividend yield zone summary (Weiss methodology).
"""

from __future__ import annotations

from utils.chart_theme import style_figure

from typing import Dict, List, Optional, Tuple

import pandas as pd

from services.yield_channel_chart import YieldChannelData, YieldChannelService

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

ZONE_CATEGORY_META: Dict[str, Dict[str, str]] = {
    "green": {
        "label": "Green — Buy zone",
        "short": "Green",
        "color": "#2e7d32",
        "emoji": "🟢",
    },
    "yellow": {
        "label": "Yellow — Fair value",
        "short": "Yellow",
        "color": "#f9a825",
        "emoji": "🟡",
    },
    "red": {
        "label": "Red — Caution / expensive",
        "short": "Red",
        "color": "#c62828",
        "emoji": "🔴",
    },
    "unknown": {
        "label": "No yield data",
        "short": "Unknown",
        "color": "#9e9e9e",
        "emoji": "⚪",
    },
}


def zone_to_category(zone: str) -> str:
    """Map Weiss yield zone to green / yellow / red."""
    if zone in ("Deep Value", "Value"):
        return "green"
    if zone == "Fair Value":
        return "yellow"
    if zone in ("Caution", "Expensive"):
        return "red"
    return "unknown"


def build_zone_dataframe(
    yield_channels: Dict[str, YieldChannelData],
    *,
    labels: Optional[Dict[str, str]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Build one row per holding with yield-zone fields."""
    labels = labels or {}
    weights = weights or {}
    rows: List[dict] = []

    for symbol, channel in sorted(yield_channels.items()):
        category = zone_to_category(channel.zone)
        meta = ZONE_CATEGORY_META[category]
        zone_info = YieldChannelService.get_zone_info(channel.zone)
        gap_fair = (
            ((channel.fair_value_price / channel.current_price) - 1) * 100
            if channel.current_price
            else None
        )
        rows.append(
            {
                "Ticker": symbol,
                "Company": channel.company_name or labels.get(symbol, symbol),
                "Zone": channel.zone,
                "Category": meta["short"],
                "CategoryKey": category,
                "Color": meta["color"],
                "Emoji": meta["emoji"],
                "ZoneEmoji": zone_info.get("emoji", ""),
                "Current Yield %": channel.current_yield,
                "Median Yield %": channel.median_yield,
                "Percentile": channel.percentile,
                "Zone Score": channel.zone_score,
                "Gap to Fair %": gap_fair,
                "Current Price": channel.current_price,
                "Fair Value Price": channel.fair_value_price,
                "Portfolio Weight %": weights.get(symbol),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Ticker",
                "Company",
                "Zone",
                "Category",
                "CategoryKey",
                "Color",
                "Emoji",
                "ZoneEmoji",
                "Current Yield %",
                "Median Yield %",
                "Percentile",
                "Zone Score",
                "Gap to Fair %",
                "Current Price",
                "Fair Value Price",
                "Portfolio Weight %",
            ]
        )

    return pd.DataFrame(rows).sort_values(
        ["CategoryKey", "Percentile"],
        ascending=[True, False],
    )


def summarize_categories(zone_df: pd.DataFrame) -> Dict[str, int]:
    """Count holdings per green / yellow / red."""
    if zone_df.empty:
        return {"green": 0, "yellow": 0, "red": 0, "unknown": 0}
    counts = zone_df["CategoryKey"].value_counts().to_dict()
    return {
        "green": int(counts.get("green", 0)),
        "yellow": int(counts.get("yellow", 0)),
        "red": int(counts.get("red", 0)),
        "unknown": int(counts.get("unknown", 0)),
    }


def create_category_count_chart(zone_df: pd.DataFrame) -> Optional["go.Figure"]:
    """Donut chart of holdings by green / yellow / red."""
    if not PLOTLY_AVAILABLE or zone_df.empty:
        return None

    counts = summarize_categories(zone_df)
    labels: List[str] = []
    values: List[int] = []
    colors: List[str] = []

    for key in ("green", "yellow", "red"):
        count = counts[key]
        if count <= 0:
            continue
        meta = ZONE_CATEGORY_META[key]
        labels.append(f"{meta['emoji']} {meta['short']} ({count})")
        values.append(count)
        colors.append(meta["color"])

    if not values:
        return None

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.45,
                marker=dict(colors=colors),
                textinfo="label+percent",
                hovertemplate="%{label}<br>%{value} holdings<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Holdings by yield zone",
        height=320,
        margin=dict(t=50, b=20, l=20, r=20),
        showlegend=False,
    )
    return style_figure(fig)


def create_position_zone_chart(zone_df: pd.DataFrame) -> Optional["go.Figure"]:
    """Horizontal bar chart: each ticker colored by zone category."""
    if not PLOTLY_AVAILABLE or zone_df.empty:
        return None

    ordered = zone_df.sort_values("Percentile", ascending=True)
    tickers = [f"{row['Emoji']} {row['Ticker']}" for _, row in ordered.iterrows()]

    fig = go.Figure(
        go.Bar(
            y=tickers,
            x=ordered["Percentile"],
            orientation="h",
            marker_color=ordered["Color"].tolist(),
            customdata=ordered[
                ["Ticker", "Zone", "Current Yield %", "Gap to Fair %"]
            ].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Zone: %{customdata[1]}<br>"
                "Yield: %{customdata[2]:.2f}%<br>"
                "Percentile: %{x:.0f}<br>"
                "Gap to fair: %{customdata[3]:+.1f}%<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="Yield percentile by holding (higher = more attractive)",
        xaxis_title="Historical yield percentile",
        yaxis_title="",
        height=max(400, 28 * len(ordered)),
        margin=dict(l=10, r=10, t=50, b=40),
        xaxis=dict(range=[0, 100]),
    )
    return style_figure(fig)


def tickers_missing_zones(
    all_symbols: List[str],
    yield_channels: Dict[str, YieldChannelData],
) -> List[str]:
    """Symbols with no preloaded yield-channel data."""
    return [symbol for symbol in all_symbols if symbol not in yield_channels]
