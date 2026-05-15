"""
Portfolio-wide dividend history and growth since 2021 (from vector DB).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from config import VECTORDB_DIR
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.vector_store import VectorStore

try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

SINCE_YEAR = 2021


@dataclass
class SymbolDividendGrowth:
    symbol: str
    company: str
    annual_by_year: Dict[int, float]
    growth_years: int
    cagr_since_start: Optional[float]
    latest_annual: Optional[float]
    shares: float


class PortfolioDividendGrowthService:
    """Annual dividend per share and portfolio cash from vector DB history."""

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        portfolio_store: Optional[PortfolioStore] = None,
    ) -> None:
        self._vector_store = vector_store
        self.portfolio = portfolio_store or PortfolioStore()

    @property
    def vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = VectorStore(persist_directory=str(VECTORDB_DIR))
        return self._vector_store

    def _annual_dividends_from_history(
        self,
        records,
        *,
        since_year: int = SINCE_YEAR,
    ) -> Dict[int, float]:
        totals: Dict[int, float] = defaultdict(float)
        for record in records:
            year = record.ex_date.year
            if year >= since_year:
                totals[year] += float(record.amount)
        return dict(sorted(totals.items()))

    @staticmethod
    def _consecutive_growth_years(annual: Dict[int, float]) -> int:
        years = sorted(annual)
        if len(years) < 2:
            return 0
        streak = 0
        for index in range(len(years) - 1, 0, -1):
            year = years[index]
            prev = years[index - 1]
            if annual[year] > annual[prev]:
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _cagr(annual: Dict[int, float]) -> Optional[float]:
        years = sorted(annual)
        if len(years) < 2:
            return None
        start_year, end_year = years[0], years[-1]
        start_val, end_val = annual[start_year], annual[end_year]
        if start_val <= 0 or end_val <= 0:
            return None
        span = end_year - start_year
        if span <= 0:
            return None
        return round(((end_val / start_val) ** (1 / span) - 1) * 100, 2)

    def build_symbol_growth(self, since_year: int = SINCE_YEAR) -> List[SymbolDividendGrowth]:
        holdings = {h.symbol: h for h in self.portfolio.list_holdings()}
        results: List[SymbolDividendGrowth] = []

        for symbol, holding in sorted(holdings.items()):
            doc = self.vector_store.get_by_symbol(symbol)
            if not doc or not doc.dividend_history:
                continue
            annual = self._annual_dividends_from_history(
                doc.dividend_history, since_year=since_year
            )
            if not annual:
                continue
            results.append(
                SymbolDividendGrowth(
                    symbol=symbol,
                    company=doc.name or symbol,
                    annual_by_year=annual,
                    growth_years=self._consecutive_growth_years(annual),
                    cagr_since_start=self._cagr(annual),
                    latest_annual=annual[max(annual)],
                    shares=holding.shares,
                )
            )
        return results

    def annual_matrix_dataframe(
        self, symbols: Optional[List[SymbolDividendGrowth]] = None
    ) -> pd.DataFrame:
        items = symbols if symbols is not None else self.build_symbol_growth()
        if not items:
            return pd.DataFrame()

        years = sorted(
            {year for item in items for year in item.annual_by_year}
        )
        rows = []
        for item in items:
            row = {"Ticker": item.symbol, "Company": item.company}
            for year in years:
                row[str(year)] = item.annual_by_year.get(year)
            row["Growth years"] = item.growth_years
            row["CAGR %"] = item.cagr_since_start
            rows.append(row)
        return pd.DataFrame(rows)

    def portfolio_cash_by_year(
        self, symbols: Optional[List[SymbolDividendGrowth]] = None
    ) -> pd.DataFrame:
        """Estimated annual dividend cash = annual DPS × shares."""
        items = symbols if symbols is not None else self.build_symbol_growth()
        totals: Dict[int, float] = defaultdict(float)
        for item in items:
            for year, dps in item.annual_by_year.items():
                totals[year] += dps * item.shares
        return pd.DataFrame(
            [{"Year": year, "Est. dividends $": round(value, 2)} for year, value in sorted(totals.items())]
        )

    def yoy_growth_matrix(
        self, symbols: Optional[List[SymbolDividendGrowth]] = None
    ) -> pd.DataFrame:
        items = symbols if symbols is not None else self.build_symbol_growth()
        if not items:
            return pd.DataFrame()

        years = sorted({year for item in items for year in item.annual_by_year})
        rows = []
        for item in items:
            row = {"Ticker": item.symbol}
            sorted_years = sorted(item.annual_by_year)
            for index, year in enumerate(sorted_years):
                if index == 0:
                    row[str(year)] = None
                    continue
                prev = sorted_years[index - 1]
                prev_val = item.annual_by_year[prev]
                curr_val = item.annual_by_year[year]
                if prev_val > 0:
                    row[str(year)] = round((curr_val - prev_val) / prev_val * 100, 1)
                else:
                    row[str(year)] = None
            rows.append(row)
        return pd.DataFrame(rows)

    def create_annual_heatmap(self, symbols: Optional[List[SymbolDividendGrowth]] = None):
        if not PLOTLY_AVAILABLE:
            return None
        items = symbols if symbols is not None else self.build_symbol_growth()
        if not items:
            return None

        items_sorted = sorted(items, key=lambda item: item.latest_annual or 0, reverse=True)
        years = sorted({year for item in items for year in item.annual_by_year})
        y_labels = [f"{item.symbol}" for item in items_sorted]
        z = [
            [item.annual_by_year.get(year) for year in years]
            for item in items_sorted
        ]

        fig = go.Figure(
            go.Heatmap(
                z=z,
                x=[str(year) for year in years],
                y=y_labels,
                colorscale="Greens",
                hovertemplate="%{y} %{x}<br>$%{z:.4f}/share<extra></extra>",
            )
        )
        fig.update_layout(
            title=f"Annual dividend / share (since {SINCE_YEAR})",
            height=max(480, 18 * len(items_sorted)),
            margin=dict(t=50, b=40, l=60),
        )
        return fig

    def create_growth_lines_chart(
        self,
        symbols: Optional[List[SymbolDividendGrowth]] = None,
        *,
        max_lines: int = 20,
    ):
        if not PLOTLY_AVAILABLE:
            return None
        items = symbols if symbols is not None else self.build_symbol_growth()
        if not items:
            return None

        ranked = sorted(
            items,
            key=lambda item: (item.cagr_since_start or 0, item.growth_years),
            reverse=True,
        )[:max_lines]

        fig = go.Figure()
        for item in ranked:
            years = sorted(item.annual_by_year)
            fig.add_trace(
                go.Scatter(
                    x=[str(year) for year in years],
                    y=[item.annual_by_year[year] for year in years],
                    mode="lines+markers",
                    name=item.symbol,
                    hovertemplate=(
                        f"<b>{item.symbol}</b><br>"
                        "%{x}<br>$%{y:.4f}/share<extra></extra>"
                    ),
                )
            )
        fig.update_layout(
            title=f"Dividend / share growth (top {len(ranked)} CAGR, since {SINCE_YEAR})",
            yaxis_title="USD / share / year",
            height=480,
            margin=dict(t=50, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        return fig

    def create_portfolio_cash_chart(
        self, symbols: Optional[List[SymbolDividendGrowth]] = None
    ):
        if not PLOTLY_AVAILABLE:
            return None
        cash_df = self.portfolio_cash_by_year(symbols)
        if cash_df.empty:
            return None

        fig = go.Figure(
            go.Bar(
                x=cash_df["Year"].astype(str),
                y=cash_df["Est. dividends $"],
                marker_color="#2e7d32",
                text=[f"${value:,.0f}" for value in cash_df["Est. dividends $"]],
                textposition="outside",
                hovertemplate="%{x}<br>$%{y:,.0f}<extra></extra>",
            )
        )
        fig.update_layout(
            title=f"Estimated portfolio dividends (DPS × shares, since {SINCE_YEAR})",
            yaxis_title="USD / year",
            height=380,
            margin=dict(t=50, b=40),
        )
        return fig

    def create_yoy_heatmap(self, symbols: Optional[List[SymbolDividendGrowth]] = None):
        if not PLOTLY_AVAILABLE:
            return None
        items = symbols if symbols is not None else self.build_symbol_growth()
        if not items:
            return None

        yoy = self.yoy_growth_matrix(items)
        if yoy.empty:
            return None

        years = [column for column in yoy.columns if column != "Ticker"]
        z = []
        for _, row in yoy.iterrows():
            z.append([row[year] if pd.notna(row[year]) else None for year in years])

        fig = go.Figure(
            go.Heatmap(
                z=z,
                x=years,
                y=yoy["Ticker"].tolist(),
                colorscale="RdYlGn",
                zmid=0,
                hovertemplate="%{y} %{x}<br>%{z:+.1f}%<extra></extra>",
            )
        )
        fig.update_layout(
            title="YoY dividend / share growth (%)",
            height=max(480, 18 * len(yoy)),
            margin=dict(t=50, b=40, l=60),
        )
        return fig
