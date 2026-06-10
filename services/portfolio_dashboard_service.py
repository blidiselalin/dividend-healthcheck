"""
High-level portfolio dashboard: KPIs and monthly evolution since inception.
"""

from __future__ import annotations

from utils.chart_theme import evolution_chart_margins, monthly_category_axis, style_figure

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from data_ingestion.deposits_store import MonthlyDeposit
from services.portfolio_deposits_service import DepositsSummary, PortfolioDepositsService

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
    profit_pct: Optional[float]
    annual_dividend_income_usd: float
    lifetime_dividends_usd: float


@dataclass
class PortfolioDashboardMetrics:
    deposits: DepositsSummary
    avg_monthly_deposit_eur: float
    cagr_pct: Optional[float]
    months_since_start: int
    best_month_label: str
    best_month_gain_pct: Optional[float]
    latest_mom_change_pct: Optional[float]
    holdings: Optional[HoldingsSnapshot] = None


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

    def __init__(self, deposits_service: Optional[PortfolioDepositsService] = None) -> None:
        self.deposits_service = deposits_service or PortfolioDepositsService()

    @staticmethod
    def _empty_evolution_frame() -> pd.DataFrame:
        return pd.DataFrame(columns=list(_EVOLUTION_COLUMNS))

    def list_deposits(self) -> List[MonthlyDeposit]:
        return self.deposits_service.list_deposits()

    def evolution_dataframe(self, deposits: Optional[List[MonthlyDeposit]] = None) -> pd.DataFrame:
        """Monthly series for charts: deposits, portfolio, cumulative capital, returns."""
        records = deposits if deposits is not None else self.list_deposits()
        if not records:
            return self._empty_evolution_frame()

        cumulative_deposits: List[float] = []
        running = 0.0
        rows = []
        prev_portfolio: Optional[float] = None

        for item in records:
            running += item.deposit_eur
            cumulative_deposits.append(running)

            portfolio = item.portfolio_eur if item.portfolio_eur > 0 else None
            gain_vs_deposits = (
                round(portfolio - running, 2) if portfolio is not None else None
            )
            mom_pct = None
            if portfolio is not None and prev_portfolio is not None and prev_portfolio > 0:
                mom_pct = round((portfolio - prev_portfolio) / prev_portfolio * 100, 2)

            rows.append(
                {
                    "period": item.period,
                    "label": item.label,
                    "deposit_eur": item.deposit_eur,
                    "deposit_usd": item.deposit_usd,
                    "portfolio_eur": portfolio,
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
        deposits: Optional[List[MonthlyDeposit]] = None,
        holdings: Optional[HoldingsSnapshot] = None,
    ) -> PortfolioDashboardMetrics:
        records = deposits if deposits is not None else self.list_deposits()
        summary = self.deposits_service.summarize(records)

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

            start_portfolio = next(
                (item.portfolio_eur for item in records if item.portfolio_eur > 0),
                None,
            )
            end_portfolio = summary.latest_portfolio_eur
            if (
                start_portfolio
                and end_portfolio
                and start_portfolio > 0
                and years >= 0.25
            ):
                cagr_pct = round(
                    ((end_portfolio / start_portfolio) ** (1 / years) - 1) * 100, 2
                )

        df = self.evolution_dataframe(records)
        best_label = ""
        best_mom = None
        latest_mom = None
        if (
            not df.empty
            and "mom_change_pct" in df.columns
            and df["mom_change_pct"].notna().any()
        ):
            valid = df.dropna(subset=["mom_change_pct"])
            if not valid.empty:
                best_idx = valid["mom_change_pct"].idxmax()
                best_label = str(valid.loc[best_idx, "label"])
                best_mom = float(valid.loc[best_idx, "mom_change_pct"])
            latest_valid = df.dropna(subset=["mom_change_pct"])
            if not latest_valid.empty:
                latest_mom = float(latest_valid.iloc[-1]["mom_change_pct"])

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
    def holdings_from_rows(rows) -> HoldingsSnapshot:
        total_value = sum(row.current_value or 0.0 for row in rows)
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

    def create_evolution_chart(self, deposits: Optional[List[MonthlyDeposit]] = None):
        """Portfolio € and cumulative deposits since inception."""
        if not PLOTLY_AVAILABLE:
            return None
        df = self.evolution_dataframe(deposits)
        if df.empty:
            return None

        plot_df = df[df["portfolio_eur"].notna()].copy()
        if plot_df.empty:
            return None

        labels = plot_df["label"].tolist()
        n_labels = len(labels)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=plot_df["cumulative_deposits_eur"],
                name="Capital deposited (cumulative)",
                mode="lines",
                line=dict(color="#5c6bc0", width=2, dash="dot"),
                hovertemplate="%{x}<br>€%{y:,.2f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=plot_df["portfolio_eur"],
                name="Portfolio value",
                mode="lines+markers",
                line=dict(color="#2e7d32", width=3),
                fill="tonexty",
                fillcolor="rgba(46, 125, 50, 0.12)",
                hovertemplate="%{x}<br>€%{y:,.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Portfolio vs deposited capital (since inception)",
            yaxis_title="€",
            height=420,
            margin=evolution_chart_margins(n_labels),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=1.08,
                x=0,
                xanchor="left",
                font=dict(size=10),
            ),
            hovermode="x unified",
        )
        fig.update_xaxes(**monthly_category_axis(n_labels))
        return style_figure(fig)

    def create_monthly_flow_chart(self, deposits: Optional[List[MonthlyDeposit]] = None):
        """Monthly deposits and portfolio month-over-month change."""
        if not PLOTLY_AVAILABLE:
            return None
        df = self.evolution_dataframe(deposits)
        if df.empty:
            return None

        labels = df["label"].tolist()
        n_labels = len(labels)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=labels,
                y=df["deposit_eur"],
                name="Monthly deposit",
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
                name="Portfolio change %",
                mode="lines+markers",
                line=dict(color="#ef6c00", width=2),
                connectgaps=False,
                hovertemplate="%{x}<br>%{y:+.2f}%<extra></extra>",
            ),
            secondary_y=True,
        )
        fig.update_layout(
            title="Monthly flow: deposits and portfolio % change",
            height=380,
            margin=evolution_chart_margins(n_labels),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=1.08,
                x=0,
                xanchor="left",
                font=dict(size=10),
            ),
        )
        fig.update_xaxes(**monthly_category_axis(n_labels))
        fig.update_yaxes(title_text="Deposit €", secondary_y=False)
        fig.update_yaxes(title_text="MoM %", secondary_y=True)
        return style_figure(fig)

    def create_gain_chart(self, deposits: Optional[List[MonthlyDeposit]] = None):
        """Unrealized gain vs cumulative deposits over time."""
        if not PLOTLY_AVAILABLE:
            return None
        df = self.evolution_dataframe(deposits)
        if df.empty or "gain_vs_deposits_eur" not in df.columns:
            return None
        plot_df = df.dropna(subset=["gain_vs_deposits_eur"])
        if plot_df.empty:
            return None

        n_labels = len(plot_df)
        colors = [
            "#2e7d32" if value >= 0 else "#c62828"
            for value in plot_df["gain_vs_deposits_eur"]
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
            title="Unrealized gain vs total deposits (€)",
            yaxis_title="€",
            height=360,
            margin=evolution_chart_margins(n_labels),
        )
        fig.update_xaxes(**monthly_category_axis(n_labels))
        return style_figure(fig)
