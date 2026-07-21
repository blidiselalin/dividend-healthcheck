"""
Portfolio-wide dividend history and growth since 2021 (from the shared market library).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from sqlite3 import Error as SQLiteError
from typing import Any

import pandas as pd

from data_ingestion.portfolio_store import PortfolioStore
from utils.chart_theme import PALETTE, bottom_legend, outside_bar_text, style_figure

try:
    from psycopg import Error as PostgresError
except ImportError:
    PostgresError = type("PostgresError", (Exception,), {})

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
    annual_by_year: dict[int, float]
    growth_years: int
    cagr_since_start: float | None
    latest_annual: float | None
    shares: float
    first_owned_year: int | None = None  # year user first held this stock


class PortfolioDividendGrowthService:
    """Annual dividend per share and portfolio cash from market library history."""

    def __init__(
        self,
        vector_store: Any | None = None,
        portfolio_store: PortfolioStore | None = None,
        journal_store: Any | None = None,
    ) -> None:
        self._vector_store = vector_store
        self.portfolio = portfolio_store or PortfolioStore(seed=False)
        self._journal_store = journal_store

    @property
    def vector_store(self) -> Any:
        if self._vector_store is None:
            from services.shared_market_db import get_shared_vector_store

            self._vector_store = get_shared_vector_store()
        return self._vector_store

    @property
    def journal_store(self) -> Any:
        if self._journal_store is None:
            from data_ingestion.purchase_journal_store import PurchaseJournalStore

            self._journal_store = PurchaseJournalStore(seed=False)
        return self._journal_store

    def _first_owned_years(self) -> dict[str, int]:
        """Return {symbol: first_year_owned} from the purchase journal."""
        result: dict[str, int] = {}
        try:
            for purchase in self.journal_store.list_purchases():
                year = purchase.purchase_date.year
                if purchase.symbol not in result or year < result[purchase.symbol]:
                    result[purchase.symbol] = year
        except (SQLiteError, PostgresError, OSError) as exc:
            import logging

            logging.getLogger(__name__).debug(
                "Could not read purchase journal for ownership tracking: %s", exc
            )
        return result

    def _annual_dividends_from_history(
        self,
        records: Any,
        *,
        since_year: int = SINCE_YEAR,
        document: Any = None,
    ) -> dict[int, float]:
        totals: dict[int, float] = defaultdict(float)
        counts: dict[int, int] = defaultdict(int)
        for record in records:
            year = record.ex_date.year
            if year >= since_year:
                totals[year] += float(record.amount)
                counts[year] += 1

        from utils.yield_history_tables import estimate_annual_dividend_for_year

        today = date.today()
        if today.year in totals:
            display, _, _ = estimate_annual_dividend_for_year(
                today.year,
                totals[today.year],
                counts[today.year],
                document=document,
                all_records=records,
                today=today,
            )
            totals[today.year] = display
        return dict(sorted(totals.items()))

    @staticmethod
    def _consecutive_growth_years(annual: dict[int, float]) -> int:
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
    def _cagr(annual: dict[int, float]) -> float | None:
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
        return float(round(((end_val / start_val) ** (1 / span) - 1) * 100, 2))

    def build_symbol_growth(self, since_year: int = SINCE_YEAR) -> list[SymbolDividendGrowth]:
        holdings = {h.symbol: h for h in self.portfolio.list_holdings()}
        if not holdings:
            return []

        # Batch-fetch all documents in one query instead of N individual round-trips.
        docs = self.vector_store.get_by_symbols(list(holdings.keys()))

        # Determine first year each symbol was owned from the purchase journal,
        # falling back to the holding's dividend_tracking_since date.
        journal_first_years = self._first_owned_years()

        results: list[SymbolDividendGrowth] = []
        for symbol, holding in sorted(holdings.items()):
            doc = docs.get(symbol.upper())
            if not doc or not doc.dividend_history:
                continue
            annual = self._annual_dividends_from_history(
                doc.dividend_history,
                since_year=since_year,
                document=doc,
            )
            if not annual:
                continue

            # Resolve first year: journal > tracking_since > None
            first_owned_year: int | None = journal_first_years.get(symbol)
            if first_owned_year is None and holding.dividend_tracking_since is not None:
                first_owned_year = holding.dividend_tracking_since.year

            results.append(
                SymbolDividendGrowth(
                    symbol=symbol,
                    company=doc.name or symbol,
                    annual_by_year=annual,
                    growth_years=self._consecutive_growth_years(annual),
                    cagr_since_start=self._cagr(annual),
                    latest_annual=annual[max(annual)],
                    shares=holding.shares,
                    first_owned_year=first_owned_year,
                )
            )
        return results

    def annual_matrix_dataframe(
        self, symbols: list[SymbolDividendGrowth] | None = None
    ) -> pd.DataFrame:
        items = symbols if symbols is not None else self.build_symbol_growth()
        if not items:
            return pd.DataFrame()

        from utils.yield_history_tables import year_column_label

        years = sorted({year for item in items for year in item.annual_by_year})
        rows = []
        for item in items:
            row: dict[str, Any] = {"Ticker": item.symbol, "Company": item.company}
            for year in years:
                row[year_column_label(year, estimated=False)] = item.annual_by_year.get(year)
            row["Growth years"] = item.growth_years
            row["CAGR %"] = item.cagr_since_start
            rows.append(row)
        return pd.DataFrame(rows)

    def portfolio_cash_by_year(
        self, symbols: list[SymbolDividendGrowth] | None = None
    ) -> pd.DataFrame:
        """Estimated annual dividend cash = annual DPS x shares.

        Only counts cash for years in which the user actually held the stock.
        Years before ``first_owned_year`` are skipped so that the bar chart
        reflects dividends actually *received*, not theoretical pre-ownership values.
        """
        items = symbols if symbols is not None else self.build_symbol_growth()
        totals: dict[int, float] = defaultdict(float)
        for item in items:
            for year, dps in item.annual_by_year.items():
                if item.first_owned_year is not None and year < item.first_owned_year:
                    continue
                totals[year] += dps * item.shares
        from utils.yield_history_tables import year_column_label

        return pd.DataFrame(
            [
                {
                    "Year": year_column_label(year, estimated=False),
                    "Est. dividends $": round(value, 2),
                }
                for year, value in sorted(totals.items())
            ]
        )

    def yoy_growth_matrix(self, symbols: list[SymbolDividendGrowth] | None = None) -> pd.DataFrame:
        items = symbols if symbols is not None else self.build_symbol_growth()
        if not items:
            return pd.DataFrame()

        from utils.yield_history_tables import year_column_label

        rows = []
        for item in items:
            row: dict[str, Any] = {"Ticker": item.symbol}
            sorted_years = sorted(item.annual_by_year)
            for index, year in enumerate(sorted_years):
                label = year_column_label(year, estimated=False)
                if index == 0:
                    row[label] = None
                    continue
                prev = sorted_years[index - 1]
                prev_val = item.annual_by_year[prev]
                curr_val = item.annual_by_year[year]
                if prev_val > 0:
                    row[label] = round((curr_val - prev_val) / prev_val * 100, 1)
                else:
                    row[label] = None
            rows.append(row)
        return pd.DataFrame(rows)

    def create_annual_heatmap(self, symbols: list[SymbolDividendGrowth] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        items = symbols if symbols is not None else self.build_symbol_growth()
        if not items:
            return None

        from utils.yield_history_tables import year_column_label

        items_sorted = sorted(items, key=lambda item: item.latest_annual or 0, reverse=True)
        years = sorted({year for item in items for year in item.annual_by_year})
        year_labels = [year_column_label(year, estimated=False) for year in years]
        y_labels = [f"{item.symbol}" for item in items_sorted]
        z = [[item.annual_by_year.get(year) for year in years] for item in items_sorted]

        fig = go.Figure(
            go.Heatmap(
                z=z,
                x=year_labels,
                y=y_labels,
                colorscale="Greens",
                colorbar={"title": "$/share", "thickness": 14, "len": 0.8},
                hovertemplate="%{y} %{x}<br>$%{z:.4f}/share<extra></extra>",
            )
        )
        fig.update_layout(
            title=f"Annual Dividend per Share Since {SINCE_YEAR}",
            height=max(480, 18 * len(items_sorted)),
            margin={"t": 60, "b": 40, "l": 60},
        )
        return style_figure(fig)

    def create_growth_lines_chart(
        self,
        symbols: list[SymbolDividendGrowth] | None = None,
        *,
        max_lines: int = 20,
    ) -> Any:
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

        from utils.yield_history_tables import year_column_label

        fig = go.Figure()
        for item in ranked:
            years = sorted(item.annual_by_year)
            fig.add_trace(
                go.Scatter(
                    x=[year_column_label(year, estimated=False) for year in years],
                    y=[item.annual_by_year[year] for year in years],
                    mode="lines+markers",
                    name=item.symbol,
                    hovertemplate=(
                        f"<b>{item.symbol}</b><br>%{{x}}<br>$%{{y:.4f}}/share<extra></extra>"
                    ),
                )
            )
        fig.update_layout(
            title=f"Dividend Growth — Top {len(ranked)} by CAGR Since {SINCE_YEAR}",
            yaxis_title="Dividend per Share (USD / year)",
            height=480,
            margin={"t": 60, "b": 60},
            legend=bottom_legend(),
        )
        return style_figure(fig)

    def create_portfolio_cash_chart(self, symbols: list[SymbolDividendGrowth] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        cash_df = self.portfolio_cash_by_year(symbols)
        if cash_df.empty:
            return None

        fig = go.Figure(
            go.Bar(
                x=cash_df["Year"].astype(str),
                y=cash_df["Est. dividends $"],
                marker_color=PALETTE["income"],
                text=[f"${value:,.0f}" for value in cash_df["Est. dividends $"]],
                hovertemplate="%{x}<br>$%{y:,.0f}<extra></extra>",
                **outside_bar_text(),
            )
        )
        fig.update_layout(
            title=(
                f"Estimated portfolio dividends received (DPS x shares owned, since {SINCE_YEAR})"
            ),
            yaxis_title="Estimated Income (USD / year)",
            height=380,
            margin={"t": 60, "b": 40},
        )
        return style_figure(fig)

    def create_yoy_heatmap(self, symbols: list[SymbolDividendGrowth] | None = None) -> Any:
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
                colorbar={"title": "%", "thickness": 14, "len": 0.8},
                hovertemplate="%{y} %{x}<br>%{z:+.1f}%<extra></extra>",
            )
        )
        fig.update_layout(
            title="Year-over-Year Dividend Growth per Share (%)",
            height=max(480, 18 * len(yoy)),
            margin={"t": 60, "b": 40, "l": 60},
        )
        return style_figure(fig)
