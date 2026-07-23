"""
High-level portfolio dashboard: KPIs and monthly evolution since inception.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from data_ingestion.deposits_store import MonthlyDeposit
from services.portfolio_deposits_service import DepositsSummary, PortfolioDepositsService
from services.portfolio_monthly_valuation import (
    compute_monthly_portfolio_valuations,
    continuous_monthly_deposits,
    pick_portfolio_eur_for_month,
)
from utils.chart_theme import (
    bottom_legend,
    evolution_chart_margins,
    monthly_category_axis,
    style_figure,
)

if TYPE_CHECKING:
    from services.portfolio_details_service import PortfolioDetailRow

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


@dataclass
class HoldingsSnapshot:
    positions: int
    current_value_usd: float
    acquisition_value_usd: float
    profit_usd: float
    profit_pct: float | None
    annual_dividend_income_usd: float
    lifetime_dividends_usd: float


@dataclass
class PortfolioDashboardMetrics:
    deposits: DepositsSummary
    avg_monthly_deposit_eur: float
    cagr_pct: float | None
    months_since_start: int
    best_month_label: str
    best_month_gain_pct: float | None
    latest_mom_change_pct: float | None
    holdings: HoldingsSnapshot | None = None


_EVOLUTION_COLUMNS = (
    "period",
    "label",
    "deposit_eur",
    "deposit_usd",
    "portfolio_eur",
    "cumulative_deposits_eur",
    "gain_vs_deposits_eur",
    "mom_change_pct",
)


class PortfolioDashboardService:
    """Aggregate deposits history and optional live holdings into dashboard KPIs."""

    def __init__(self, deposits_service: PortfolioDepositsService | None = None) -> None:
        self.deposits_service = deposits_service or PortfolioDepositsService()

    @staticmethod
    def _empty_evolution_frame() -> pd.DataFrame:
        return pd.DataFrame(columns=list(_EVOLUTION_COLUMNS))

    def list_deposits(self) -> list[MonthlyDeposit]:
        return self.deposits_service.list_deposits()

    def _valuation_db_path(self, db_path: Path | None) -> Path | None:
        if db_path is not None:
            return db_path
        store = getattr(self.deposits_service, "store", None)
        path = getattr(store, "db_path", None)
        return Path(path) if path is not None else None

    def evolution_dataframe(
        self,
        deposits: list[MonthlyDeposit] | None = None,
        *,
        db_path: Path | None = None,
        use_computed_portfolio: bool = True,
    ) -> pd.DataFrame:
        """Monthly series for charts: deposits, portfolio, cumulative capital, returns."""
        records = deposits if deposits is not None else self.list_deposits()
        if not records:
            return self._empty_evolution_frame()

        records = continuous_monthly_deposits(records)
        computed: dict[str, Any] = {}
        valuation_path = self._valuation_db_path(db_path)
        if use_computed_portfolio:
            try:
                computed = compute_monthly_portfolio_valuations(records, db_path=valuation_path)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Monthly portfolio valuation skipped: %s", exc)

        cumulative_deposits: list[float] = []
        running = 0.0
        rows = []
        prev_portfolio: float | None = None

        for item in records:
            running += item.deposit_eur
            cumulative_deposits.append(running)

            calculated = computed.get(item.period_key)
            stored = item.portfolio_eur if item.portfolio_eur > 0 else None
            portfolio = pick_portfolio_eur_for_month(stored=stored, valuation=calculated)
            gain_vs_deposits = round(portfolio - running, 2) if portfolio is not None else None
            mom_pct = None
            if portfolio is not None and prev_portfolio is not None and prev_portfolio > 0:
                net_flow = item.deposit_eur
                mom_pct = round(
                    (portfolio - prev_portfolio - net_flow) / prev_portfolio * 100,
                    2,
                )

            rows.append(
                {
                    "period_key": item.period_key,
                    "period": item.period,
                    "label": item.label,
                    "deposit_eur": item.deposit_eur,
                    "deposit_usd": item.deposit_usd,
                    "portfolio_eur": portfolio,
                    "portfolio_eur_stored": stored,
                    "portfolio_eur_computed": (
                        calculated.portfolio_eur if calculated is not None else None
                    ),
                    "portfolio_coverage": (
                        round(calculated.coverage, 4) if calculated is not None else None
                    ),
                    "cumulative_deposits_eur": running,
                    "gain_vs_deposits_eur": gain_vs_deposits,
                    "mom_change_pct": mom_pct,
                }
            )
            if portfolio is not None:
                prev_portfolio = portfolio

        return pd.DataFrame(rows)

    def build_metrics(
        self,
        deposits: list[MonthlyDeposit] | None = None,
        holdings: HoldingsSnapshot | None = None,
        *,
        db_path: Path | None = None,
    ) -> PortfolioDashboardMetrics:
        records = deposits if deposits is not None else self.list_deposits()
        summary = self.deposits_service.summarize(records)

        df = self.evolution_dataframe(records, db_path=self._valuation_db_path(db_path))
        if not df.empty and df["portfolio_eur"].notna().any():
            latest_row = df.dropna(subset=["portfolio_eur"]).iloc[-1]
            summary = DepositsSummary(
                total_deposits_eur=summary.total_deposits_eur,
                total_deposits_usd=summary.total_deposits_usd,
                latest_portfolio_eur=float(latest_row["portfolio_eur"]),
                latest_label=str(latest_row["label"]),
                month_count=summary.month_count,
                gain_eur=round(
                    float(latest_row["portfolio_eur"])
                    - float(latest_row["cumulative_deposits_eur"]),
                    2,
                ),
                gain_pct=(
                    round(
                        (
                            float(latest_row["portfolio_eur"])
                            - float(latest_row["cumulative_deposits_eur"])
                        )
                        / float(latest_row["cumulative_deposits_eur"])
                        * 100,
                        2,
                    )
                    if float(latest_row["cumulative_deposits_eur"]) > 0
                    else None
                ),
            )

        avg_deposit = (
            summary.total_deposits_eur / summary.month_count if summary.month_count else 0.0
        )

        cagr_pct = None
        months_since = 0
        if len(records) >= 2:
            start = records[0].period
            end = records[-1].period
            months_since = (end.year - start.year) * 12 + (end.month - start.month)
            years = months_since / 12.0 if months_since > 0 else 0

            valued = df.dropna(subset=["portfolio_eur"]) if not df.empty else df
            start_portfolio = float(valued.iloc[0]["portfolio_eur"]) if not valued.empty else None
            end_portfolio = summary.latest_portfolio_eur
            if start_portfolio and end_portfolio and start_portfolio > 0 and years >= 0.25:
                cagr_pct = round(((end_portfolio / start_portfolio) ** (1 / years) - 1) * 100, 2)

        best_label = ""
        best_mom = None
        latest_mom = None
        if not df.empty and "mom_change_pct" in df.columns and df["mom_change_pct"].notna().any():
            valid = df.dropna(subset=["mom_change_pct"])
            if not valid.empty:
                best_idx = valid["mom_change_pct"].idxmax()
                best_label = str(valid.loc[best_idx, "label"])
                best_mom = float(str(valid.loc[best_idx, "mom_change_pct"]))
            latest_valid = df.dropna(subset=["mom_change_pct"])
            if not latest_valid.empty:
                latest_mom = float(str(latest_valid.iloc[-1]["mom_change_pct"]))

        return PortfolioDashboardMetrics(
            deposits=summary,
            avg_monthly_deposit_eur=round(avg_deposit, 2),
            cagr_pct=cagr_pct,
            months_since_start=months_since,
            best_month_label=best_label,
            best_month_gain_pct=best_mom,
            latest_mom_change_pct=latest_mom,
            holdings=holdings,
        )

    @staticmethod
    def holdings_from_rows(rows: list[PortfolioDetailRow]) -> HoldingsSnapshot:
        total_value = sum(row.current_value for row in rows if row.current_value is not None)
        total_acquisition = sum(row.acquisition_value for row in rows)
        profit = total_value - total_acquisition
        profit_pct = (profit / total_acquisition * 100) if total_acquisition else None
        return HoldingsSnapshot(
            positions=len(rows),
            current_value_usd=total_value,
            acquisition_value_usd=total_acquisition,
            profit_usd=profit,
            profit_pct=profit_pct,
            annual_dividend_income_usd=sum(row.annual_income or 0.0 for row in rows),
            lifetime_dividends_usd=sum(row.dividends_paid for row in rows),
        )

    def create_evolution_chart(
        self,
        deposits: list[MonthlyDeposit] | None = None,
        *,
        db_path: Path | None = None,
        use_computed_portfolio: bool = True,
    ) -> Any:
        """Portfolio € and cumulative deposits since inception."""
        if not PLOTLY_AVAILABLE:
            return None
        df = self.evolution_dataframe(
            deposits,
            db_path=db_path,
            use_computed_portfolio=use_computed_portfolio,
        )
        if df.empty:
            return None

        labels = df["label"].tolist()
        n_labels = len(labels)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=df["cumulative_deposits_eur"],
                name="Deposits (cumul.)",
                mode="lines",
                line={"color": "#5c6bc0", "width": 2, "dash": "dot"},
                hovertemplate="%{x}<br>€%{y:,.2f}<extra></extra>",
            )
        )
        portfolio_series = df["portfolio_eur"]
        if not portfolio_series.notna().any():
            return None
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=portfolio_series,
                name="Portfolio",
                mode="lines+markers",
                line={"color": "#2e7d32", "width": 3},
                connectgaps=True,
                fill="tonexty",
                fillcolor="rgba(46, 125, 50, 0.12)",
                hovertemplate="%{x}<br>€%{y:,.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            yaxis_title="€",
            height=420,
            margin=evolution_chart_margins(n_labels, legend_bottom=True),
            legend=bottom_legend(),
            hovermode="x unified",
        )
        fig.update_xaxes(**monthly_category_axis(n_labels))
        return style_figure(fig)

    def create_monthly_flow_chart(
        self,
        deposits: list[MonthlyDeposit] | None = None,
        *,
        db_path: Path | None = None,
    ) -> Any:
        """Monthly deposits and portfolio month-over-month change."""
        if not PLOTLY_AVAILABLE:
            return None
        df = self.evolution_dataframe(deposits, db_path=self._valuation_db_path(db_path))
        if df.empty:
            return None

        labels = df["label"].tolist()
        n_labels = len(labels)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=labels,
                y=df["deposit_eur"],
                name="Deposit",
                marker_color="#1976d2",
                opacity=0.85,
                hovertemplate="%{x}<br>Deposit €%{y:,.2f}<extra></extra>",
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=df["mom_change_pct"],
                name="MoM %",
                mode="lines+markers",
                line={"color": "#ef6c00", "width": 2},
                connectgaps=False,
                hovertemplate="%{x}<br>%{y:+.2f}%<extra></extra>",
            ),
            secondary_y=True,
        )
        fig.update_layout(
            height=380,
            margin=evolution_chart_margins(n_labels, legend_bottom=True, dual_y=True),
            legend=bottom_legend(),
        )
        fig.update_xaxes(**monthly_category_axis(n_labels))
        fig.update_yaxes(title_text="€", secondary_y=False)
        fig.update_yaxes(title_text="%", secondary_y=True)
        return style_figure(fig)

    def create_gain_chart(
        self,
        deposits: list[MonthlyDeposit] | None = None,
        *,
        db_path: Path | None = None,
    ) -> Any:
        """Unrealized gain vs cumulative deposits over time."""
        if not PLOTLY_AVAILABLE:
            return None
        df = self.evolution_dataframe(deposits, db_path=self._valuation_db_path(db_path))
        if df.empty or "gain_vs_deposits_eur" not in df.columns:
            return None
        plot_df = df.dropna(subset=["gain_vs_deposits_eur"])
        if plot_df.empty:
            return None

        n_labels = len(plot_df)
        colors = [
            "#2e7d32" if value >= 0 else "#c62828" for value in plot_df["gain_vs_deposits_eur"]
        ]
        fig = go.Figure(
            go.Bar(
                x=plot_df["label"],
                y=plot_df["gain_vs_deposits_eur"],
                marker_color=colors,
                hovertemplate="%{x}<br>€%{y:+,.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            yaxis_title="€",
            height=360,
            margin=evolution_chart_margins(n_labels),
            showlegend=False,
        )
        fig.update_xaxes(**monthly_category_axis(n_labels))
        return style_figure(fig)
