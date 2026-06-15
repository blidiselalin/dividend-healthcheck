"""
Hypothetical benchmark portfolios from monthly index/ETF share purchases.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from data_ingestion.benchmark_purchases_seed import (
    BENCHMARK_META,
    BENCHMARK_SHARES_BY_PERIOD,
)
from data_ingestion.deposits_store import DepositsStore, MonthlyDeposit
from db.benchmark_store import BenchmarkPriceStore
from utils.chart_theme import (
    PALETTE,
    bottom_legend,
    evolution_chart_margins,
    monthly_category_axis,
    outside_bar_text,
    style_figure,
)

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
    import yfinance as yf

    YFINANCE_AVAILABLE = True
    PLOTLY_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    PLOTLY_AVAILABLE = False


@dataclass(frozen=True)
class BenchmarkDefinition:
    key: str
    display_symbol: str
    yfinance_symbol: str
    label: str


BENCHMARKS: list[BenchmarkDefinition] = [
    BenchmarkDefinition(key, display, yf_sym, label)
    for key, display, yf_sym, label in BENCHMARK_META
]

FOCUS_LABELS = {
    "Portfolio": "Portfolio €",
    "S&P 500": "S&P 500 €",
    "SCHD": "SCHD €",
}

# ETF proxies when index tickers fail on Yahoo Finance
YFINANCE_FALLBACKS: dict[str, str] = {
    "^GSPC": "SPY",
    "^DJI": "DIA",
    "^IXIC": "QQQ",
}


def _month_end(day: date) -> date:
    last = calendar.monthrange(day.year, day.month)[1]
    return date(day.year, day.month, last)


def _eur_usd_rate(deposit: MonthlyDeposit) -> float:
    if deposit.deposit_usd and deposit.deposit_usd > 0 and deposit.deposit_eur > 0:
        return deposit.deposit_eur / deposit.deposit_usd
    return 0.92


class PortfolioBenchmarkService:
    """Value benchmark buy-and-hold paths vs actual portfolio (EUR)."""

    def __init__(self, deposits_store: DepositsStore | None = None) -> None:
        self.store = deposits_store or DepositsStore()

    def get_benchmark_shares(self, deposit: MonthlyDeposit) -> dict[str, float]:
        key = deposit.period_key
        values = BENCHMARK_SHARES_BY_PERIOD.get(key, (0.0, 0.0, 0.0, 0.0))
        return {
            "sp500": values[0],
            "schd": values[1],
            "dji": values[2],
            "nasdaq": values[3],
        }

    def _download_close_series(self, symbol: str, start: date, end: date) -> pd.Series[Any]:
        if not YFINANCE_AVAILABLE:
            return pd.Series(dtype=float)
        candidates = [symbol]
        fallback = YFINANCE_FALLBACKS.get(symbol)
        if fallback:
            candidates.append(fallback)
        for candidate in candidates:
            try:
                frame = yf.download(
                    candidate,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    progress=False,
                    auto_adjust=True,
                )
            except Exception:  # noqa: S112
                continue
            if frame is None or frame.empty:
                continue
            if "Close" in frame.columns:
                series = frame["Close"].dropna()
            else:
                series = frame.iloc[:, 0].dropna()
            if not series.empty:
                return series
        return pd.Series(dtype=float)

    def _fetch_month_end_prices(
        self,
        deposits: list[MonthlyDeposit],
    ) -> dict[str, dict[str, float]]:
        """period_key -> {benchmark_key: month-end close USD}.

        Prices are loaded from the persistent ``benchmark_price_history`` table
        first.  Any symbol whose stored history does not reach the last deposit
        month is (re-)fetched from Yahoo Finance and then persisted so future
        calls do not need a network request.
        """
        if not deposits:
            return {}

        start = deposits[0].period
        end = _month_end(deposits[-1].period) + timedelta(days=5)

        price_store = BenchmarkPriceStore()
        # Seed ETF metadata once (no-op if already present)
        try:
            price_store.seed_etf_info_if_empty()
        except Exception:  # pragma: no cover
            pass

        closes: dict[str, pd.Series[Any]] = {}
        for benchmark in BENCHMARKS:
            sym = benchmark.yfinance_symbol
            # Check whether stored data covers the requested range.
            latest = price_store.latest_date(sym)
            need_fetch = latest is None or latest < _month_end(deposits[-1].period)

            if need_fetch and YFINANCE_AVAILABLE:
                fetch_start = (latest + timedelta(days=1)) if latest else start
                series = self._download_close_series(sym, fetch_start, end)
                if not series.empty:
                    # Persist new rows to the store.
                    try:
                        price_store.upsert_prices(
                            sym,
                            {
                                ts.date() if hasattr(ts, "date") else ts: float(val)
                                for ts, val in series.items()
                                if val is not None
                            },
                        )
                    except Exception:  # pragma: no cover
                        pass

            # Load the full range from the store (combines persisted + newly fetched).
            stored = price_store.load_prices(sym, start, end)
            if stored:
                idx = pd.to_datetime(list(stored.keys()))
                closes[benchmark.key] = pd.Series(list(stored.values()), index=idx)
            elif YFINANCE_AVAILABLE:
                # Fallback: use in-memory series if store is unavailable.
                series = self._download_close_series(sym, start, end)
                if not series.empty:
                    closes[benchmark.key] = series

        result: dict[str, dict[str, float]] = {}
        for deposit in deposits:
            month_end = _month_end(deposit.period)
            period_prices: dict[str, float] = {}
            for key, series in closes.items():
                eligible = series[series.index <= pd.Timestamp(month_end)]
                if eligible.empty:
                    continue
                val = eligible.iloc[-1]
                if val is not None and isinstance(val, (int, float)):
                    period_prices[key] = float(val)
            result[deposit.period_key] = period_prices
        return result

    def refresh_benchmark_prices(self) -> dict[str, int]:
        """Force-fetch all benchmark symbols from Yahoo Finance and persist results.

        Returns ``{yfinance_symbol: rows_written}`` for each benchmark.
        Useful for an admin "Refresh benchmark prices" button.
        """
        if not YFINANCE_AVAILABLE:
            return {}

        deposits = self.store.list_deposits()
        if not deposits:
            return {}

        start = deposits[0].period
        end = _month_end(deposits[-1].period) + timedelta(days=5)
        price_store = BenchmarkPriceStore()
        results: dict[str, int] = {}

        for benchmark in BENCHMARKS:
            sym = benchmark.yfinance_symbol
            series = self._download_close_series(sym, start, end)
            if series.empty:
                results[sym] = 0
                continue
            try:
                written = price_store.upsert_prices(
                    sym,
                    {
                        ts.date() if hasattr(ts, "date") else ts: float(val)
                        for ts, val in series.items()
                        if val is not None
                    },
                )
                results[sym] = written
            except Exception as exc:
                logger.warning("Could not persist prices for %s: %s", sym, exc)
                results[sym] = 0

        return results

    def build_comparison_dataframe(
        self,
        deposits: list[MonthlyDeposit] | None = None,
    ) -> pd.DataFrame:
        records = deposits if deposits is not None else self.store.list_deposits()
        if not records:
            return pd.DataFrame()

        prices = self._fetch_month_end_prices(records)
        cumulative: dict[str, float] = {benchmark.key: 0.0 for benchmark in BENCHMARKS}
        rows = []

        for deposit in records:
            purchases = self.get_benchmark_shares(deposit)
            for key, shares in purchases.items():
                cumulative[key] = cumulative.get(key, 0.0) + shares

            fx = _eur_usd_rate(deposit)
            month_prices = prices.get(deposit.period_key, {})
            row = {
                "Year": deposit.period.year,
                "Month": deposit.label,
                "Deposit €": deposit.deposit_eur,
                "Deposit $": deposit.deposit_usd,
                "Portfolio €": deposit.portfolio_eur if deposit.portfolio_eur > 0 else None,
            }
            for benchmark in BENCHMARKS:
                price = month_prices.get(benchmark.key)
                if price is None or cumulative[benchmark.key] <= 0:
                    row[f"{benchmark.label} $"] = None
                    row[f"{benchmark.label} €"] = None
                else:
                    value_usd = cumulative[benchmark.key] * price
                    row[f"{benchmark.label} $"] = round(value_usd, 2)
                    row[f"{benchmark.label} €"] = round(value_usd * fx, 2)
                row[f"{benchmark.label} shares"] = round(cumulative[benchmark.key], 4)

            rows.append(row)

        return pd.DataFrame(rows)

    def latest_comparison(
        self,
        comparison_df: pd.DataFrame,
        deposits: list[MonthlyDeposit],
    ) -> dict[str, float]:
        """Latest portfolio EUR vs benchmark EUR (last row with portfolio value)."""
        if comparison_df.empty:
            return {}

        portfolio_eur = None
        for deposit in reversed(deposits):
            if deposit.portfolio_eur > 0:
                portfolio_eur = deposit.portfolio_eur
                break

        last_row = comparison_df.iloc[-1]
        out = {"Portfolio": portfolio_eur or 0.0}
        for benchmark in BENCHMARKS:
            col = f"{benchmark.label} €"
            value = last_row.get(col)
            out[benchmark.label] = (
                float(str(value)) if value is not None and pd.notna(value) else 0.0
            )
        return out

    def create_comparison_chart(
        self,
        deposits: list[MonthlyDeposit] | None = None,
    ) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        df = self.build_comparison_dataframe(deposits)
        if df.empty:
            return None

        labels = df["Month"].tolist()
        fig = go.Figure()

        portfolio = df["Portfolio €"]
        if portfolio.notna().any():
            fig.add_trace(
                go.Scatter(
                    x=labels,
                    y=portfolio,
                    name="Portfolio (actual)",
                    mode="lines+markers",
                    line={"color": "#2e7d32", "width": 3},
                    connectgaps=True,
                    hovertemplate="%{x}<br>€%{y:,.0f}<extra></extra>",
                )
            )

        colors = ["#1565c0", "#6a1b9a", "#ef6c00", "#00838f"]
        for benchmark, color in zip(BENCHMARKS, colors, strict=False):
            col = f"{benchmark.label} €"
            if col not in df.columns:
                continue
            series = df[col]
            if series.notna().any():
                fig.add_trace(
                    go.Scatter(
                        x=labels,
                        y=series,
                        name=f"{benchmark.label} (DCA shares)",
                        mode="lines",
                        line={"color": color, "width": 1.8, "dash": "dot"},
                        connectgaps=True,
                        hovertemplate="%{x}<br>€%{y:,.0f}<extra></extra>",
                    )
                )

        fig.update_layout(
            title="Portfolio vs All Benchmarks — Same Monthly Purchases",
            yaxis_title="Value (€, USD converted at deposit FX rate)",
            height=480,
            margin=evolution_chart_margins(len(labels), legend_bottom=True),
            legend=bottom_legend(),
            hovermode="x unified",
        )
        fig.update_xaxes(**monthly_category_axis(len(labels)))
        return style_figure(fig)

    def build_yearly_summary(self, comparison_df: pd.DataFrame) -> pd.DataFrame:
        """Per-calendar-year deposits, year-end values, and YoY returns."""
        if comparison_df.empty or "Year" not in comparison_df.columns:
            return pd.DataFrame()

        years = sorted(comparison_df["Year"].unique())
        rows: list[dict[str, Any]] = []
        prior_ends: dict[str, float | None] = {name: None for name in FOCUS_LABELS}

        for year in years:
            year_df = comparison_df[comparison_df["Year"] == year]
            deposits = float(year_df["Deposit €"].sum())
            ends: dict[str, float | None] = {}
            row: dict[str, Any] = {"Year": int(year), "Deposits €": round(deposits, 2)}
            for name, col in FOCUS_LABELS.items():
                if col not in year_df.columns:
                    ends[name] = None
                    continue
                valid = year_df[col].dropna()
                val = valid.iloc[-1] if not valid.empty else None
                ends[name] = float(str(val)) if val is not None else None

            for name, end_val in ends.items():
                row[f"{name} (EOY) €"] = round(end_val, 2) if end_val is not None else None
                prior_val = prior_ends[name]
                if end_val is not None and prior_val is not None and prior_val > 0:
                    row[f"{name} YoY %"] = round((end_val - prior_val) / prior_val * 100, 2)
                else:
                    row[f"{name} YoY %"] = None
                prior_ends[name] = end_val

            rows.append(row)

        return pd.DataFrame(rows)

    def create_focused_comparison_chart(self, comparison_df: pd.DataFrame) -> Any:
        """Portfolio vs S&P 500 vs SCHD over time."""
        if not PLOTLY_AVAILABLE or comparison_df.empty:
            return None

        labels = comparison_df["Month"].tolist()
        fig = go.Figure()
        styles = [
            ("Portfolio €", "Portfolio", "#2e7d32", "lines+markers", 3, None),
            ("S&P 500 €", "S&P 500", "#1565c0", "lines", 2.5, "dot"),
            ("SCHD €", "SCHD", "#6a1b9a", "lines", 2.5, "dash"),
        ]
        for col, name, color, mode, width, dash in styles:
            if col not in comparison_df.columns:
                continue
            series = comparison_df[col]
            if not series.notna().any():
                continue
            fig.add_trace(
                go.Scatter(
                    x=labels,
                    y=series,
                    name=name,
                    mode=mode,
                    line={"color": color, "width": width, "dash": dash},
                    connectgaps=True,
                    hovertemplate="%{x}<br>€%{y:,.0f}<extra></extra>",
                )
            )

        fig.update_layout(
            title="Portfolio vs S&P 500 vs SCHD — Monthly Value",
            yaxis_title="Value (€)",
            height=440,
            margin=evolution_chart_margins(len(labels), legend_bottom=True),
            legend=bottom_legend(),
            hovermode="x unified",
        )
        fig.update_xaxes(**monthly_category_axis(len(labels)))
        return style_figure(fig)

    def create_yearly_end_values_chart(self, yearly_df: pd.DataFrame) -> Any:
        """Grouped bars: year-end portfolio vs benchmarks each year."""
        if not PLOTLY_AVAILABLE or yearly_df.empty:
            return None

        years = yearly_df["Year"].astype(str).tolist()
        fig = go.Figure()
        series_specs = [
            ("Portfolio (EOY) €", "Portfolio", "#2e7d32"),
            ("S&P 500 (EOY) €", "S&P 500", "#1565c0"),
            ("SCHD (EOY) €", "SCHD", "#6a1b9a"),
        ]
        for col, name, color in series_specs:
            if col not in yearly_df.columns:
                continue
            fig.add_trace(
                go.Bar(
                    x=years,
                    y=yearly_df[col],
                    name=name,
                    marker_color=color,
                    hovertemplate="%{x}<br>€%{y:,.0f}<extra></extra>",
                )
            )

        fig.update_layout(
            title="Year-End Value — Portfolio vs S&P 500 vs SCHD",
            barmode="group",
            yaxis_title="Year-End Value (€)",
            height=400,
            margin={"t": 60, "b": 40},
            legend=bottom_legend(),
        )
        return style_figure(fig)

    def create_yearly_returns_chart(self, yearly_df: pd.DataFrame) -> Any:
        """Grouped bars: YoY % return per year for each series."""
        if not PLOTLY_AVAILABLE or yearly_df.empty:
            return None

        years = yearly_df["Year"].astype(str).tolist()
        fig = go.Figure()
        return_cols = [
            ("Portfolio YoY %", "Portfolio", "#2e7d32"),
            ("S&P 500 YoY %", "S&P 500", "#1565c0"),
            ("SCHD YoY %", "SCHD", "#6a1b9a"),
        ]
        for col, name, color in return_cols:
            if col not in yearly_df.columns:
                continue
            fig.add_trace(
                go.Bar(
                    x=years,
                    y=yearly_df[col],
                    name=name,
                    marker_color=color,
                    hovertemplate="%{x}<br>%{y:+.1f}%<extra></extra>",
                )
            )

        fig.update_layout(
            title="Annual Return (YoY %) — Portfolio vs S&P 500 vs SCHD",
            barmode="group",
            yaxis_title="Year-over-Year Return (%)",
            height=400,
            margin={"t": 60, "b": 40},
            legend=bottom_legend(),
        )
        return style_figure(fig)

    def create_yearly_distribution_chart(self, yearly_df: pd.DataFrame) -> Any:
        """
        Stacked 100% bars per year: share of combined EOY value
        (Portfolio vs S&P 500 vs SCHD).
        """
        if not PLOTLY_AVAILABLE or yearly_df.empty:
            return None

        years = yearly_df["Year"].astype(str).tolist()
        value_cols = [
            ("Portfolio (EOY) €", "Portfolio", "#2e7d32"),
            ("S&P 500 (EOY) €", "S&P 500", "#1565c0"),
            ("SCHD (EOY) €", "SCHD", "#6a1b9a"),
        ]

        totals: list[float | None] = []
        for _, row in yearly_df.iterrows():
            total = sum(
                float(row[col])
                for col, _, _ in value_cols
                if col in yearly_df.columns and pd.notna(row[col]) and row[col] > 0
            )
            totals.append(total if total > 0 else None)

        fig = go.Figure()
        for col, name, color in value_cols:
            if col not in yearly_df.columns:
                continue
            shares: list[float | None] = []
            for index, (_, row) in enumerate(yearly_df.iterrows()):
                val = row[col]
                yearly_total = totals[index]
                if pd.isna(val) or yearly_total is None or yearly_total == 0:
                    shares.append(None)
                else:
                    shares.append(float(val) / yearly_total * 100)
            fig.add_trace(
                go.Bar(
                    x=years,
                    y=shares,
                    name=name,
                    marker_color=color,
                    hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
                )
            )

        fig.update_layout(
            title="Annual Value Distribution — Portfolio vs Benchmarks (%)",
            barmode="stack",
            yaxis_title="Share of Combined EOY Value (%)",
            height=400,
            margin={"t": 60, "b": 40},
            legend=bottom_legend(),
        )
        return style_figure(fig)

    def create_yearly_deposits_chart(self, yearly_df: pd.DataFrame) -> Any:
        """Deposits per calendar year."""
        if not PLOTLY_AVAILABLE or yearly_df.empty or "Deposits €" not in yearly_df.columns:
            return None

        years = yearly_df["Year"].astype(str).tolist()
        fig = go.Figure(
            go.Bar(
                x=years,
                y=yearly_df["Deposits €"],
                marker_color=PALETTE["deposit"],
                text=[f"€{value:,.0f}" for value in yearly_df["Deposits €"]],
                hovertemplate="%{x}<br>€%{y:,.0f}<extra></extra>",
                **outside_bar_text(),
            )
        )
        fig.update_layout(
            title="Deposits per Calendar Year",
            yaxis_title="Amount Deposited (€)",
            height=340,
            margin={"t": 60, "b": 40},
        )
        return style_figure(fig)
