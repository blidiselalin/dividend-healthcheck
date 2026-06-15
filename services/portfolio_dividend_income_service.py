"""
Charts and summaries for net dividend income (after tax).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from data_ingestion.dividend_income_store import (
    MONTH_LABELS,
    DividendIncomeStore,
    MonthlyNetDividend,
    dividend_tax_rate,
)
from utils.chart_theme import (
    PALETTE,
    bottom_legend,
    evolution_chart_margins,
    monthly_category_axis,
    outside_bar_text,
    style_figure,
)

try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


@dataclass
class DividendIncomeSummary:
    total_net_usd: float
    total_gross_usd: float
    total_tax_usd: float
    ytd_net_usd: float
    ytd_year: int
    best_year: int
    best_year_net: float
    avg_monthly_net: float
    month_count: int


class PortfolioDividendIncomeService:
    def __init__(self, store: DividendIncomeStore | None = None) -> None:
        self.store = store or DividendIncomeStore()

    def list_dividends(self) -> list[MonthlyNetDividend]:
        return self.store.list_dividends()

    def detail_dataframe(self, records: list[MonthlyNetDividend] | None = None) -> pd.DataFrame:
        items = records if records is not None else self.list_dividends()
        return pd.DataFrame(
            [
                {
                    "Year": item.year,
                    "Month": item.month_label,
                    "Net $": item.net_usd,
                    "Gross $": item.gross_usd,
                    "Tax %": item.tax_rate_pct,
                    "Tax withheld $": item.tax_withheld_usd,
                }
                for item in items
            ]
        )

    def pivot_net_dataframe(self, records: list[MonthlyNetDividend] | None = None) -> pd.DataFrame:
        """Rows = month (Ian–Dec), columns = years (like spreadsheet)."""  # noqa: RUF002
        items = records if records is not None else self.list_dividends()
        if not items:
            return pd.DataFrame()

        years = sorted({item.year for item in items})
        matrix: dict[str, dict[int, float | None]] = {
            label: {year: None for year in years} for label in MONTH_LABELS
        }
        for item in items:
            matrix[item.month_label][item.year] = item.net_usd

        rows = []
        for label in MONTH_LABELS:
            row: dict[str, Any] = {"Month": label}
            for year in years:
                value = matrix[label][year]
                row[str(year)] = value
            rows.append(row)
        return pd.DataFrame(rows)

    def yearly_summary(self, records: list[MonthlyNetDividend] | None = None) -> pd.DataFrame:
        items = records if records is not None else self.list_dividends()
        if not items:
            return pd.DataFrame()

        by_year: dict[int, dict[str, Any]] = {}
        for item in items:
            bucket = by_year.setdefault(
                item.year,
                {"net": 0.0, "gross": 0.0, "tax": 0.0, "months": 0},
            )
            bucket["net"] += item.net_usd
            bucket["gross"] += item.gross_usd
            bucket["tax"] += item.tax_withheld_usd
            bucket["months"] += 1

        rows = []
        for year in sorted(by_year):
            bucket = by_year[year]
            rows.append(
                {
                    "Year": year,
                    "Tax %": dividend_tax_rate(year) * 100,
                    "Months": bucket["months"],
                    "Net $": round(bucket["net"], 2),
                    "Gross $": round(bucket["gross"], 2),
                    "Tax withheld $": round(bucket["tax"], 2),
                }
            )
        return pd.DataFrame(rows)

    def summarize(
        self,
        records: list[MonthlyNetDividend] | None = None,
        *,
        ytd_year: int | None = None,
        rows: list[Any] | None = None,
    ) -> DividendIncomeSummary:
        items = records if records is not None else self.list_dividends()
        if not items:
            return DividendIncomeSummary(0, 0, 0, 0, ytd_year or 2026, 0, 0, 0, 0)

        total_net = sum(item.net_usd for item in items)
        total_gross = sum(item.gross_usd for item in items)
        total_tax = sum(item.tax_withheld_usd for item in items)
        year = ytd_year or items[-1].year
        ytd_net = sum(item.net_usd for item in items if item.year == year)

        yearly = self.yearly_summary(items)
        best_row = yearly.loc[yearly["Net $"].idxmax()]

        if rows:
            from data_ingestion.dividend_income_store import dividend_tax_rate

            total_annual_gross = sum(row.annual_income or 0.0 for row in rows)
            tax_rate = dividend_tax_rate(year)
            estimated_annual_net = total_annual_gross * (1.0 - tax_rate)
            avg_monthly = estimated_annual_net / 12.0
        else:
            avg_monthly = total_net / len(items) if items else 0.0

        return DividendIncomeSummary(
            total_net_usd=round(total_net, 2),
            total_gross_usd=round(total_gross, 2),
            total_tax_usd=round(total_tax, 2),
            ytd_net_usd=round(ytd_net, 2),
            ytd_year=year,
            best_year=int(best_row["Year"]),
            best_year_net=float(best_row["Net $"]),
            avg_monthly_net=round(avg_monthly, 2),
            month_count=len(items),
        )

    def timeline_dataframe(self, records: list[MonthlyNetDividend] | None = None) -> pd.DataFrame:
        items = records if records is not None else self.list_dividends()
        cumulative = 0.0
        rows = []
        for item in items:
            cumulative += item.net_usd
            rows.append(
                {
                    "label": f"{item.month_label} {item.year}",
                    "year": item.year,
                    "net_usd": item.net_usd,
                    "cumulative_net_usd": round(cumulative, 2),
                }
            )
        return pd.DataFrame(rows)

    def create_yearly_bar_chart(self, records: list[MonthlyNetDividend] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        yearly = self.yearly_summary(records)
        if yearly.empty:
            return None
        fig = go.Figure(
            go.Bar(
                x=yearly["Year"].astype(str),
                y=yearly["Net $"],
                name="Net",
                marker_color=PALETTE["income"],
                text=[f"${value:,.0f}" for value in yearly["Net $"]],
                hovertemplate="%{x}<br>Net $%{y:,.2f}<extra></extra>",
                **outside_bar_text(),
            )
        )
        fig.update_layout(
            title="Net Dividends per Year",
            yaxis_title="Net Income (USD)",
            height=380,
            margin={"t": 60, "b": 40},
        )
        return style_figure(fig)

    def create_monthly_by_year_chart(self, records: list[MonthlyNetDividend] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        items = records if records is not None else self.list_dividends()
        if not items:
            return None

        df = pd.DataFrame(
            [
                {
                    "year": str(item.year),
                    "month": item.month_label,
                    "net": item.net_usd,
                    "sort": item.month,
                }
                for item in items
            ]
        )
        fig = go.Figure()
        for year in sorted(df["year"].unique()):
            subset = df[df["year"] == year].sort_values("sort")
            fig.add_trace(
                go.Bar(
                    x=subset["month"],
                    y=subset["net"],
                    name=year,
                    hovertemplate="%{x} %{fullData.name}<br>$%{y:,.2f}<extra></extra>",
                )
            )
        fig.update_layout(
            title="Monthly Net Dividends — Year Comparison",
            barmode="group",
            yaxis_title="Net Income (USD)",
            height=420,
            margin={"t": 60, "b": 60},
            legend=bottom_legend(),
        )
        return style_figure(fig)

    def create_cumulative_chart(self, records: list[MonthlyNetDividend] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        timeline = self.timeline_dataframe(records)
        if timeline.empty:
            return None
        n = len(timeline)
        fig = go.Figure(
            go.Scatter(
                x=timeline["label"],
                y=timeline["cumulative_net_usd"],
                mode="lines+markers",
                fill="tozeroy",
                fillcolor=f"rgba(21, 101, 192, 0.12)",
                line={"color": PALETTE["deposit"], "width": 2.5},
                marker={"size": 5},
                hovertemplate="%{x}<br>Cumulative $%{y:,.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Cumulative Net Dividends Since Inception",
            yaxis_title="Cumulative Net Income (USD)",
            height=400,
            margin=evolution_chart_margins(n),
        )
        fig.update_xaxes(**monthly_category_axis(n))
        return style_figure(fig)

    def create_heatmap_chart(self, records: list[MonthlyNetDividend] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        pivot = self.pivot_net_dataframe(records)
        if pivot.empty:
            return None

        years = [column for column in pivot.columns if column != "Month"]
        z = []
        for _, row in pivot.iterrows():
            z.append([row[y] if pd.notna(row[y]) else 0 for y in years])

        fig = go.Figure(
            go.Heatmap(
                z=z,
                x=years,
                y=pivot["Month"].tolist(),
                colorscale="Greens",
                colorbar={"title": "USD", "thickness": 14, "len": 0.8},
                hovertemplate="%{y} %{x}<br>$%{z:,.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Net Dividend Heatmap — Month × Year",
            height=400,
            margin={"t": 60, "b": 40},
        )
        return style_figure(fig)
