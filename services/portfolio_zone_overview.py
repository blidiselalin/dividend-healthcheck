"""
Portfolio-level dividend yield zone summary (Weiss methodology).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from services.yield_channel_chart import YieldChannelData, YieldChannelService
from utils.chart_theme import style_figure

try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

ZONE_CATEGORY_META: dict[str, dict[str, str]] = {
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
    yield_channels: dict[str, YieldChannelData],
    *,
    labels: dict[str, str] | None = None,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Build one row per holding with yield-zone fields."""
    labels = labels or {}
    weights = weights or {}
    rows: list[dict[str, Any]] = []

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


def summarize_categories(zone_df: pd.DataFrame) -> dict[str, int]:
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


def create_category_count_chart(zone_df: pd.DataFrame) -> go.Figure | None:
    """Donut chart of holdings by green / yellow / red."""
    if not PLOTLY_AVAILABLE or zone_df.empty:
        return None

    counts = summarize_categories(zone_df)
    labels: list[str] = []
    values: list[int] = []
    colors: list[str] = []

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
                marker={"colors": colors},
                textinfo="label+percent",
                hovertemplate="%{label}<br>%{value} holdings<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Holdings by Yield Zone (Weiss Methodology)",
        height=320,
        margin={"t": 60, "b": 20, "l": 20, "r": 20},
        showlegend=False,
    )
    return style_figure(fig)


def create_position_zone_chart(zone_df: pd.DataFrame) -> go.Figure | None:
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
            customdata=ordered[["Ticker", "Zone", "Current Yield %", "Gap to Fair %"]].values,
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
        title="Yield Percentile by Holding — Higher Is More Attractive",
        xaxis_title="Historical Yield Percentile",
        yaxis_title="",
        height=max(400, 28 * len(ordered)),
        margin={"l": 10, "r": 60, "t": 60, "b": 40},
        xaxis={"range": [0, 100]},
    )
    return style_figure(fig)


def tickers_missing_zones(
    all_symbols: list[str],
    yield_channels: dict[str, YieldChannelData],
) -> list[str]:
    """Symbols with no preloaded yield-channel data."""
    return [symbol for symbol in all_symbols if symbol not in yield_channels]
