"""
Purchase journal views: timeline, tables, and charts.
"""

from __future__ import annotations

from utils.chart_theme import style_figure

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore, PurchaseRecord

try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


@dataclass
class PurchaseJournalSummary:
    total_lots: int
    symbols_with_buys: int
    first_purchase: str
    last_purchase: str
    symbols_in_portfolio: int


@dataclass(frozen=True)
class EstimatedPurchaseLot:
    """One journal line with shares/value estimated from portfolio totals."""

    symbol: str
    purchase_date: date
    label: str
    price_usd: float
    estimated_shares: float
    estimated_value_usd: float


@dataclass(frozen=True)
class SymbolAcquisitionSplit:
    symbol: str
    lot_count: int
    total_shares: float
    journal_acquisition_usd: float
    db_acquisition_usd: float
    portfolio_weight_pct: float
    lots_weight_pct: float


class PortfolioPurchaseJournalService:
    def __init__(
        self,
        journal_store: Optional[PurchaseJournalStore] = None,
        portfolio_store: Optional[PortfolioStore] = None,
    ) -> None:
        if journal_store is None and portfolio_store is None:
            from services.portfolio_context import create_portfolio_context

            ctx = create_portfolio_context()
            self.journal = ctx.journal
            self.portfolio = ctx.portfolio
        else:
            anchor = journal_store or portfolio_store
            path = anchor.db_path if anchor is not None else None
            self.journal = journal_store or PurchaseJournalStore(db_path=path, seed=False)
            self.portfolio = portfolio_store or PortfolioStore(db_path=path, seed=False)

    def list_purchases(self) -> List[PurchaseRecord]:
        return self.journal.list_purchases(portfolio_only=True)

    def summarize(self, records: Optional[List[PurchaseRecord]] = None) -> PurchaseJournalSummary:
        items = records if records is not None else self.list_purchases()
        holdings = self.portfolio.list_holdings()
        if not items:
            return PurchaseJournalSummary(0, 0, "—", "—", len(holdings))

        symbols = {item.symbol for item in items}
        return PurchaseJournalSummary(
            total_lots=len(items),
            symbols_with_buys=len(symbols),
            first_purchase=items[0].label,
            last_purchase=items[-1].label,
            symbols_in_portfolio=len(holdings),
        )

    def chronological_dataframe(
        self, records: Optional[List[PurchaseRecord]] = None
    ) -> pd.DataFrame:
        items = records if records is not None else self.list_purchases()
        return pd.DataFrame(
            [
                {
                    "Date": item.label,
                    "Ticker": item.symbol,
                    "Price $": item.price_usd,
                }
                for item in items
            ]
        )

    def by_symbol_dataframe(
        self, records: Optional[List[PurchaseRecord]] = None
    ) -> pd.DataFrame:
        items = records if records is not None else self.list_purchases()
        holdings = {h.symbol: h for h in self.portfolio.list_holdings()}
        grouped: Dict[str, List[PurchaseRecord]] = defaultdict(list)
        for item in items:
            grouped[item.symbol].append(item)

        rows = []
        for symbol in sorted(holdings):
            lots = grouped.get(symbol, [])
            if not lots:
                continue
            dates = ", ".join(lot.label for lot in lots)
            prices = ", ".join(f"${lot.price_usd:.2f}" for lot in lots)
            holding = holdings[symbol]
            rows.append(
                {
                    "Ticker": symbol,
                    "Shares": holding.shares,
                    "# Purchases": len(lots),
                    "Purchase dates": dates,
                    "Prices $": prices,
                    "Avg price $": round(
                        sum(lot.price_usd for lot in lots) / len(lots), 2
                    ),
                    "DB avg cost $": holding.avg_cost_per_share,
                }
            )
        return pd.DataFrame(rows)

    def yearly_counts(self, records: Optional[List[PurchaseRecord]] = None) -> pd.DataFrame:
        items = records if records is not None else self.list_purchases()
        counts: Dict[int, int] = defaultdict(int)
        for item in items:
            counts[item.purchase_date.year] += 1
        return pd.DataFrame(
            [{"Year": year, "Purchases": count} for year, count in sorted(counts.items())]
        )

    def symbols_without_journal(self) -> List[str]:
        purchases = {item.symbol for item in self.list_purchases()}
        return sorted(
            holding.symbol
            for holding in self.portfolio.list_holdings()
            if holding.symbol not in purchases
        )

    def build_estimated_lots(
        self, records: Optional[List[PurchaseRecord]] = None
    ) -> List[EstimatedPurchaseLot]:
        """
        Split each holding's shares evenly across journal purchases, then scale
        lot values so they sum to the portfolio DB acquisition value.
        """
        items = records if records is not None else self.list_purchases()
        holdings = {h.symbol: h for h in self.portfolio.list_holdings()}
        grouped: Dict[str, List[PurchaseRecord]] = defaultdict(list)
        for item in items:
            grouped[item.symbol].append(item)

        estimates: List[EstimatedPurchaseLot] = []
        for symbol, lots in grouped.items():
            holding = holdings.get(symbol)
            if not holding or not lots:
                continue
            lots_sorted = sorted(lots, key=lambda lot: lot.purchase_date)
            shares_per_lot = holding.shares / len(lots_sorted)
            raw_values = [shares_per_lot * lot.price_usd for lot in lots_sorted]
            raw_total = sum(raw_values)
            target = holding.acquisition_value
            scale = (target / raw_total) if raw_total > 0 else 1.0

            for lot, raw_value in zip(lots_sorted, raw_values):
                value = raw_value * scale
                shares = shares_per_lot
                if lot.price_usd > 0:
                    shares = value / lot.price_usd
                estimates.append(
                    EstimatedPurchaseLot(
                        symbol=symbol,
                        purchase_date=lot.purchase_date,
                        label=lot.label,
                        price_usd=lot.price_usd,
                        estimated_shares=round(shares, 4),
                        estimated_value_usd=round(value, 2),
                    )
                )
        return estimates

    def acquisition_split(
        self, records: Optional[List[PurchaseRecord]] = None
    ) -> List[SymbolAcquisitionSplit]:
        items = records if records is not None else self.list_purchases()
        holdings = {h.symbol: h for h in self.portfolio.list_holdings()}
        estimates = self.build_estimated_lots(items)

        value_by_symbol: Dict[str, float] = defaultdict(float)
        lots_by_symbol: Dict[str, int] = defaultdict(int)
        for lot in estimates:
            value_by_symbol[lot.symbol] += lot.estimated_value_usd
            lots_by_symbol[lot.symbol] += 1

        total_value = sum(value_by_symbol.values())
        total_lots = sum(lots_by_symbol.values())

        splits: List[SymbolAcquisitionSplit] = []
        for symbol in sorted(value_by_symbol, key=value_by_symbol.get, reverse=True):
            holding = holdings[symbol]
            journal_val = value_by_symbol[symbol]
            splits.append(
                SymbolAcquisitionSplit(
                    symbol=symbol,
                    lot_count=lots_by_symbol[symbol],
                    total_shares=holding.shares,
                    journal_acquisition_usd=round(journal_val, 2),
                    db_acquisition_usd=round(holding.acquisition_value, 2),
                    portfolio_weight_pct=round(
                        (journal_val / total_value * 100) if total_value else 0, 2
                    ),
                    lots_weight_pct=round(
                        (lots_by_symbol[symbol] / total_lots * 100) if total_lots else 0,
                        2,
                    ),
                )
            )
        return splits

    def acquisition_split_dataframe(
        self, records: Optional[List[PurchaseRecord]] = None
    ) -> pd.DataFrame:
        splits = self.acquisition_split(records)
        return pd.DataFrame(
            [
                {
                    "Ticker": item.symbol,
                    "# Purchases": item.lot_count,
                    "Shares": item.total_shares,
                    "Journal value $": item.journal_acquisition_usd,
                    "DB value $": item.db_acquisition_usd,
                    "% of value": item.portfolio_weight_pct,
                    "% of trades": item.lots_weight_pct,
                }
                for item in splits
            ]
        )

    def lot_estimates_dataframe(
        self, records: Optional[List[PurchaseRecord]] = None
    ) -> pd.DataFrame:
        estimates = self.build_estimated_lots(records)
        return pd.DataFrame(
            [
                {
                    "Date": lot.label,
                    "Ticker": lot.symbol,
                    "Price $": lot.price_usd,
                    "Est. shares": lot.estimated_shares,
                    "Est. value $": lot.estimated_value_usd,
                }
                for lot in estimates
            ]
        )

    def create_acquisition_value_treemap(
        self, records: Optional[List[PurchaseRecord]] = None
    ):
        if not PLOTLY_AVAILABLE:
            return None
        splits = self.acquisition_split(records)
        if not splits:
            return None

        labels = [f"{s.symbol} ({s.lot_count})" for s in splits]
        fig = go.Figure(
            go.Treemap(
                labels=labels,
                parents=[""] * len(splits),
                values=[s.journal_acquisition_usd for s in splits],
                textinfo="label+percent entry+value",
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Value: $%{value:,.0f}<br>"
                    "%{percentRoot:.1%} of portfolio<extra></extra>"
                ),
            )
        )
        fig.update_layout(
            title="Acquisition value split (estimated from journal × shares)",
            height=480,
            margin=dict(t=50, b=20),
        )
        return style_figure(fig)

    def create_lots_count_pie(self, records: Optional[List[PurchaseRecord]] = None):
        if not PLOTLY_AVAILABLE:
            return None
        splits = self.acquisition_split(records)
        if not splits:
            return None

        top = splits[:15]
        other_lots = sum(s.lot_count for s in splits[15:])
        labels = [s.symbol for s in top]
        values = [s.lot_count for s in top]
        if other_lots:
            labels.append("Other")
            values.append(other_lots)

        fig = go.Figure(
            go.Pie(
                labels=labels,
                values=values,
                hole=0.4,
                textinfo="label+percent",
                hovertemplate="%{label}<br>%{value} purchases<br>%{percent}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Purchase count split (journal transactions)",
            height=420,
            margin=dict(t=50, b=20),
        )
        return style_figure(fig)

    def create_value_vs_lots_chart(self, records: Optional[List[PurchaseRecord]] = None):
        """Bubble: x = # lots, y = acquisition value, size = shares."""
        if not PLOTLY_AVAILABLE:
            return None
        splits = self.acquisition_split(records)
        if not splits:
            return None

        fig = go.Figure(
            go.Scatter(
                x=[s.lot_count for s in splits],
                y=[s.journal_acquisition_usd for s in splits],
                mode="markers+text",
                text=[s.symbol for s in splits],
                textposition="top center",
                marker=dict(
                    size=[max(12, min(50, s.total_shares / 2)) for s in splits],
                    color=[s.portfolio_weight_pct for s in splits],
                    colorscale="Blues",
                    showscale=True,
                    colorbar=dict(title="% value"),
                ),
                customdata=[
                    [s.symbol, s.lot_count, s.total_shares, s.db_acquisition_usd]
                    for s in splits
                ],
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[1]} purchases<br>"
                    "%{customdata[2]:.0f} shares<br>"
                    "Journal $%{y:,.0f}<br>"
                    "DB $%{customdata[3]:,.0f}<extra></extra>"
                ),
            )
        )
        fig.update_layout(
            title="Purchases vs estimated value",
            xaxis_title="# purchases (journal)",
            yaxis_title="Estimated acquisition value $",
            height=480,
            margin=dict(t=50, b=40),
        )
        return style_figure(fig)

    def create_dual_split_bar(self, records: Optional[List[PurchaseRecord]] = None):
        if not PLOTLY_AVAILABLE:
            return None
        splits = self.acquisition_split(records)
        if not splits:
            return None

        top = splits[:20]
        tickers = [s.symbol for s in top]
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                name="Acquisition value $",
                x=tickers,
                y=[s.journal_acquisition_usd for s in top],
                marker_color="#1976d2",
                yaxis="y",
                offsetgroup=0,
                hovertemplate="%{x}<br>$%{y:,.0f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Bar(
                name="# purchases",
                x=tickers,
                y=[s.lot_count for s in top],
                marker_color="#43a047",
                yaxis="y2",
                offsetgroup=1,
                hovertemplate="%{x}<br>%{y} trades<extra></extra>",
            )
        )
        fig.update_layout(
            title="Top 20: acquisition value vs number of buys",
            barmode="group",
            yaxis=dict(title="Value $"),
            yaxis2=dict(title="# purchases", overlaying="y", side="right"),
            height=440,
            margin=dict(t=50, b=120),
            xaxis=dict(tickangle=-45),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        return style_figure(fig)

    def create_timeline_chart(self, records: Optional[List[PurchaseRecord]] = None):
        if not PLOTLY_AVAILABLE:
            return None
        items = records if records is not None else self.list_purchases()
        if not items:
            return None

        symbols = sorted({item.symbol for item in items})
        symbol_y = {symbol: index for index, symbol in enumerate(symbols)}

        fig = go.Figure(
            go.Scatter(
                x=[item.purchase_date for item in items],
                y=[symbol_y[item.symbol] for item in items],
                mode="markers",
                marker=dict(size=9, color="#1976d2"),
                customdata=[
                    [item.symbol, item.label, item.price_usd] for item in items
                ],
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[1]}<br>"
                    "$%{customdata[2]:.2f}<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            title="Purchase journal — timeline",
            xaxis_title="Date",
            yaxis=dict(
                tickmode="array",
                tickvals=list(symbol_y.values()),
                ticktext=symbols,
            ),
            height=max(420, 22 * len(symbols)),
            margin=dict(t=50, b=40, l=80),
        )
        return style_figure(fig)

    def create_yearly_activity_chart(self, records: Optional[List[PurchaseRecord]] = None):
        if not PLOTLY_AVAILABLE:
            return None
        yearly = self.yearly_counts(records)
        if yearly.empty:
            return None
        fig = go.Figure(
            go.Bar(
                x=yearly["Year"].astype(str),
                y=yearly["Purchases"],
                marker_color="#43a047",
                hovertemplate="%{x}<br>%{y} purchases<extra></extra>",
            )
        )
        fig.update_layout(
            title="Purchases per year",
            yaxis_title="Transactions",
            height=340,
            margin=dict(t=50, b=40),
        )
        return style_figure(fig)

    def create_price_scatter_by_symbol(self, records: Optional[List[PurchaseRecord]] = None):
        if not PLOTLY_AVAILABLE:
            return None
        items = records if records is not None else self.list_purchases()
        if not items:
            return None

        fig = go.Figure()
        for symbol in sorted({item.symbol for item in items}):
            lots = [item for item in items if item.symbol == symbol]
            fig.add_trace(
                go.Scatter(
                    x=[lot.purchase_date for lot in lots],
                    y=[lot.price_usd for lot in lots],
                    mode="markers+lines",
                    name=symbol,
                    hovertemplate="%{fullData.name}<br>%{x}<br>$%{y:.2f}<extra></extra>",
                )
            )
        fig.update_layout(
            title="Purchase price over time (by ticker)",
            xaxis_title="Date",
            yaxis_title="Price $",
            height=440,
            margin=dict(t=50, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        return style_figure(fig)
