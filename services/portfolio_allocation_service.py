"""
Portfolio allocation by sector and market-cap bucket.
"""

from __future__ import annotations

from utils.chart_theme import style_figure

from typing import TYPE_CHECKING, List, Optional

import pandas as pd

if TYPE_CHECKING:
    from services.portfolio_details_service import PortfolioDetailRow

try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

BUCKET_ORDER = ["1–10B", "10–200B", ">200B", "<1B", "Unknown"]
BUCKET_LABELS = {
    "1–10B": "$1B – $10B",
    "10–200B": "$10B – $200B",
    ">200B": "> $200B",
    "<1B": "< $1B",
    "Unknown": "Unknown",
}


def classify_market_cap_bucket(market_cap: Optional[float]) -> str:
    """Classify market cap (USD) into portfolio buckets."""
    if market_cap is None or market_cap <= 0:
        return "Unknown"
    if market_cap < 1_000_000_000:
        return "<1B"
    if market_cap < 10_000_000_000:
        return "1–10B"
    if market_cap < 200_000_000_000:
        return "10–200B"
    return ">200B"


def _position_value(row: "PortfolioDetailRow") -> float:
    return row.current_value if row.current_value is not None else row.acquisition_value


class PortfolioAllocationService:
    """Sector and market-cap allocation from loaded portfolio rows."""

    def sector_allocation(self, rows: List["PortfolioDetailRow"]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()

        groups: dict[str, dict] = {}
        total = 0.0
        for row in rows:
            value = _position_value(row)
            if value <= 0:
                continue
            sector = (row.sector or "Unknown").strip() or "Unknown"
            bucket = groups.setdefault(
                sector,
                {"sector": sector, "value_usd": 0.0, "positions": 0},
            )
            bucket["value_usd"] += value
            bucket["positions"] += 1
            total += value

        if total <= 0:
            return pd.DataFrame()

        records = []
        for item in groups.values():
            weight = item["value_usd"] / total * 100
            records.append(
                {
                    "Sector": item["sector"],
                    "Value USD": round(item["value_usd"], 2),
                    "Weight %": round(weight, 2),
                    "Positions": item["positions"],
                }
            )
        return pd.DataFrame(records).sort_values("Weight %", ascending=False)

    def market_cap_allocation(self, rows: List["PortfolioDetailRow"]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()

        groups: dict[str, dict] = {}
        total = 0.0
        for row in rows:
            value = _position_value(row)
            if value <= 0:
                continue
            bucket = classify_market_cap_bucket(row.market_cap)
            entry = groups.setdefault(
                bucket,
                {"bucket": bucket, "value_usd": 0.0, "positions": 0},
            )
            entry["value_usd"] += value
            entry["positions"] += 1
            total += value

        if total <= 0:
            return pd.DataFrame()

        records = []
        for key in BUCKET_ORDER:
            if key not in groups:
                continue
            item = groups[key]
            weight = item["value_usd"] / total * 100
            records.append(
                {
                    "Market cap": BUCKET_LABELS.get(key, key),
                    "Bucket": key,
                    "Value USD": round(item["value_usd"], 2),
                    "Weight %": round(weight, 2),
                    "Positions": item["positions"],
                }
            )
        return pd.DataFrame(records)

    def holdings_by_bucket(self, rows: List["PortfolioDetailRow"]) -> pd.DataFrame:
        """Per-holding detail for market-cap breakdown table."""
        records = []
        for row in rows:
            value = _position_value(row)
            bucket = classify_market_cap_bucket(row.market_cap)
            cap_b = row.market_cap / 1_000_000_000 if row.market_cap else None
            records.append(
                {
                    "Ticker": row.ticker,
                    "Company": row.company,
                    "Sector": row.sector,
                    "Market cap (B)": round(cap_b, 2) if cap_b is not None else None,
                    "Bucket": BUCKET_LABELS.get(bucket, bucket),
                    "Value USD": round(value, 2) if value else None,
                    "Weight %": row.weight_pct,
                }
            )
        return pd.DataFrame(records).sort_values(
            ["Bucket", "Value USD"],
            ascending=[True, False],
            na_position="last",
        )

    def create_sector_pie(self, rows: List["PortfolioDetailRow"]):
        if not PLOTLY_AVAILABLE:
            return None
        df = self.sector_allocation(rows)
        if df.empty:
            return None
        fig = go.Figure(
            go.Pie(
                labels=df["Sector"],
                values=df["Weight %"],
                hole=0.45,
                textinfo="label+percent",
                textposition="outside",
                hovertemplate="<b>%{label}</b><br>%{percent}<br>$%{customdata:,.0f}<extra></extra>",
                customdata=df["Value USD"],
            )
        )
        fig.update_layout(
            title="Sector allocation (by portfolio weight)",
            height=420,
            margin=dict(t=50, b=20, l=20, r=20),
            showlegend=False,
        )
        return style_figure(fig)

    def create_market_cap_pie(self, rows: List["PortfolioDetailRow"]):
        if not PLOTLY_AVAILABLE:
            return None
        df = self.market_cap_allocation(rows)
        if df.empty:
            return None
        colors = {
            "1–10B": "#42a5f5",
            "10–200B": "#66bb6a",
            ">200B": "#ab47bc",
            "<1B": "#ffa726",
            "Unknown": "#bdbdbd",
        }
        fig = go.Figure(
            go.Pie(
                labels=df["Market cap"],
                values=df["Weight %"],
                hole=0.45,
                marker_colors=[colors.get(b, "#9e9e9e") for b in df["Bucket"]],
                textinfo="label+percent",
                textposition="outside",
                hovertemplate="<b>%{label}</b><br>%{percent}<br>$%{customdata:,.0f}<br>%{meta} holdings<extra></extra>",
                customdata=df["Value USD"],
                meta=df["Positions"],
            )
        )
        fig.update_layout(
            title="Market cap distribution ($1B–$10B · $10B–$200B · >$200B)",
            height=420,
            margin=dict(t=50, b=20, l=20, r=20),
            showlegend=False,
        )
        return style_figure(fig)

    def create_sector_bar(self, rows: List["PortfolioDetailRow"]):
        if not PLOTLY_AVAILABLE:
            return None
        df = self.sector_allocation(rows)
        if df.empty:
            return None
        ordered = df.sort_values("Weight %", ascending=True)
        fig = go.Figure(
            go.Bar(
                y=ordered["Sector"],
                x=ordered["Weight %"],
                orientation="h",
                marker_color="#1976d2",
                text=[f"{value:.1f}%" for value in ordered["Weight %"]],
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>%{x:.1f}%<br>$%{customdata:,.0f}<extra></extra>",
                customdata=ordered["Value USD"],
            )
        )
        fig.update_layout(
            title="Sector weights",
            xaxis_title="Portfolio weight %",
            height=max(320, 28 * len(ordered)),
            margin=dict(t=50, b=40, l=10, r=40),
        )
        return style_figure(fig)
