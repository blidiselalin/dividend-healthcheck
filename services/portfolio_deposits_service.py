"""
Summaries and charts for monthly account deposits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from data_ingestion.deposits_store import DepositsStore, MonthlyDeposit
from utils.chart_theme import (
    PALETTE,
    evolution_chart_margins,
    monthly_category_axis,
    style_figure,
)

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


@dataclass
class DepositsSummary:
    total_deposits_eur: float
    total_deposits_usd: float
    latest_portfolio_eur: float
    latest_label: str
    month_count: int
    gain_eur: float
    gain_pct: float | None


class PortfolioDepositsService:
    """Build deposit tables, totals, and charts."""

    def __init__(self, store: DepositsStore | None = None) -> None:
        self.store = store or DepositsStore()

    def list_deposits(self) -> list[MonthlyDeposit]:
        return self.store.list_deposits()

    def to_dataframe(self, deposits: list[MonthlyDeposit] | None = None) -> pd.DataFrame:
        records = deposits if deposits is not None else self.list_deposits()
        return pd.DataFrame(
            [
                {
                    "Month": item.label,
                    "Deposit €": item.deposit_eur,
                    "Deposit $": item.deposit_usd,
                    "Portfolio €": item.portfolio_eur,
                }
                for item in records
            ]
        )

    def summarize(self, deposits: list[MonthlyDeposit] | None = None) -> DepositsSummary:
        records = deposits if deposits is not None else self.list_deposits()
        total_eur = round(sum(item.deposit_eur for item in records), 2)
        total_usd = round(sum(item.deposit_usd for item in records), 2)

        latest_portfolio = 0.0
        latest_label = ""
        for item in reversed(records):
            if item.portfolio_eur > 0:
                latest_portfolio = item.portfolio_eur
                latest_label = item.label
                break
        if not latest_label and records:
            latest_label = records[-1].label
            latest_portfolio = records[-1].portfolio_eur

        gain_eur = round(latest_portfolio - total_eur, 2)
        gain_pct = (gain_eur / total_eur * 100) if total_eur > 0 else None

        deposit_months = sum(1 for item in records if item.deposit_eur > 0 or item.deposit_usd > 0)

        return DepositsSummary(
            total_deposits_eur=total_eur,
            total_deposits_usd=total_usd,
            latest_portfolio_eur=latest_portfolio,
            latest_label=latest_label,
            month_count=deposit_months,
            gain_eur=gain_eur,
            gain_pct=gain_pct,
        )

    def create_deposits_chart(self, deposits: list[MonthlyDeposit] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        records = deposits if deposits is not None else self.list_deposits()
        if not records:
            return None

        labels = [item.label for item in records]
        n = len(labels)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=labels,
                y=[item.deposit_eur for item in records],
                name="Monthly Deposit",
                marker_color=PALETTE["deposit"],
                opacity=0.85,
                hovertemplate="%{x}<br>€%{y:,.2f}<extra></extra>",
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=[item.portfolio_eur for item in records],
                name="Portfolio Value",
                mode="lines+markers",
                line={"color": PALETTE["income"], "width": 2.5},
                marker={"size": 5},
                hovertemplate="%{x}<br>€%{y:,.2f}<extra></extra>",
            ),
            secondary_y=True,
        )
        fig.update_layout(
            title="Monthly Deposits and Portfolio Value (€)",
            height=420,
            margin=evolution_chart_margins(n, legend_bottom=True, dual_y=True),
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
            hovermode="x unified",
        )
        fig.update_xaxes(**monthly_category_axis(n))
        fig.update_yaxes(title_text="Deposit (€)", secondary_y=False)
        fig.update_yaxes(title_text="Portfolio Value (€)", secondary_y=True)
        return style_figure(fig)

    def create_cumulative_chart(self, deposits: list[MonthlyDeposit] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        records = deposits if deposits is not None else self.list_deposits()
        if not records:
            return None

        cumulative_eur: list[float] = []
        running = 0.0
        for item in records:
            running += item.deposit_eur
            cumulative_eur.append(running)

        labels = [item.label for item in records]
        n = len(labels)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=labels,
                y=cumulative_eur,
                name="Cumulative Deposits",
                mode="lines+markers",
                fill="tozeroy",
                fillcolor="rgba(92, 107, 192, 0.12)",
                line={"color": "#5c6bc0", "width": 2.5},
                marker={"size": 5},
                hovertemplate="%{x}<br>€%{y:,.2f}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Cumulative Deposits (€)",
            yaxis_title="Cumulative Deposits (€)",
            height=360,
            margin=evolution_chart_margins(n),
        )
        fig.update_xaxes(**monthly_category_axis(n))
        return style_figure(fig)
