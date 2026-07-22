"""
Purchase journal views: timeline, tables, and charts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore, PurchaseRecord
from utils.chart_theme import PALETTE, bottom_legend, style_figure

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
        journal_store: PurchaseJournalStore | None = None,
        portfolio_store: PortfolioStore | None = None,
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

    def list_purchases(self, *, portfolio_only: bool = False) -> list[PurchaseRecord]:
        return self.journal.list_purchases(portfolio_only=portfolio_only)

    def summarize(self, records: list[PurchaseRecord] | None = None) -> PurchaseJournalSummary:
        items = records if records is not None else self.list_purchases()
        holdings = self.portfolio.list_open_holdings()
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

    def chronological_dataframe(self, records: list[PurchaseRecord] | None = None) -> pd.DataFrame:
        items = records if records is not None else self.list_purchases()
        return pd.DataFrame(
            [
                {
                    "Date": item.label,
                    "Ticker": item.symbol,
                    "Side": item.side.title(),
                    "Shares": item.shares,
                    "Price $": item.price_usd,
                    "Commission $": item.commission_usd,
                    "Cost $": item.lot_cost_usd,
                }
                for item in items
            ]
        )

    def by_symbol_dataframe(
        self,
        records: list[PurchaseRecord] | None = None,
        *,
        include_closed: bool = True,
    ) -> pd.DataFrame:
        items = records if records is not None else self.list_purchases()
        holdings = {h.symbol: h for h in self.portfolio.list_open_holdings()}
        grouped: dict[str, list[PurchaseRecord]] = defaultdict(list)
        for item in items:
            grouped[item.symbol].append(item)

        rows = []
        symbols = sorted(set(grouped) | (set(holdings) if include_closed else set()))
        for symbol in symbols:
            lots = grouped.get(symbol, [])
            if not lots and symbol not in holdings:
                continue
            if not include_closed and symbol not in holdings:
                continue
            dates = ", ".join(lot.label for lot in lots)
            prices = ", ".join(f"${lot.price_usd:.2f}" for lot in lots)
            holding = holdings.get(symbol)
            rows.append(
                {
                    "Ticker": symbol,
                    "Shares": holding.shares if holding is not None else 0.0,
                    "# Trades": len(lots),
                    "Trade dates": dates,
                    "Prices $": prices,
                    "Avg price $": round(sum(lot.price_usd for lot in lots) / len(lots), 2),
                    "DB avg cost $": holding.avg_cost_per_share if holding is not None else None,
                }
            )
        return pd.DataFrame(rows)

    def yearly_counts(self, records: list[PurchaseRecord] | None = None) -> pd.DataFrame:
        items = records if records is not None else self.list_purchases()
        counts: dict[int, int] = defaultdict(int)
        for item in items:
            counts[item.purchase_date.year] += 1
        return pd.DataFrame(
            [{"Year": year, "Purchases": count} for year, count in sorted(counts.items())]
        )

    def symbols_without_journal(self) -> list[str]:
        purchases = {item.symbol for item in self.list_purchases(portfolio_only=True)}
        return sorted(
            holding.symbol
            for holding in self.portfolio.list_open_holdings()
            if holding.symbol not in purchases
        )

    def build_estimated_lots(
        self,
        records: list[PurchaseRecord] | None = None,
        *,
        include_closed: bool = False,
    ) -> list[EstimatedPurchaseLot]:
        """
        Split each holding's shares across journal purchases, then scale
        lot values so they sum to the portfolio DB acquisition value.

        When ``include_closed`` is False, symbols removed from holdings after a
        full sell are omitted from portfolio analytics but remain in the journal.
        """
        items = records
        if items is None:
            items = self.journal.list_purchases(portfolio_only=False)
        holdings = {h.symbol: h for h in self.portfolio.list_open_holdings()}
        grouped: dict[str, list[PurchaseRecord]] = defaultdict(list)
        for item in items:
            grouped[item.symbol].append(item)

        estimates: list[EstimatedPurchaseLot] = []
        for symbol, lots in grouped.items():
            holding = holdings.get(symbol)
            if not include_closed and holding is None:
                continue
            lots_sorted = sorted(lots, key=lambda lot: lot.purchase_date)
            if any(lot.shares is not None and lot.shares > 0 for lot in lots_sorted):
                for lot in lots_sorted:
                    if lot.shares is None or lot.shares <= 0:
                        continue
                    shares = float(lot.shares)
                    signed = -shares if lot.side == "sell" else shares
                    value = shares * lot.price_usd + lot.commission_usd
                    if lot.side == "sell":
                        value = -value
                    estimates.append(
                        EstimatedPurchaseLot(
                            symbol=symbol,
                            purchase_date=lot.purchase_date,
                            label=lot.label,
                            price_usd=lot.price_usd,
                            estimated_shares=round(signed, 4),
                            estimated_value_usd=round(value, 2),
                        )
                    )
                continue

            if not holding or not lots:
                continue

            shares_per_lot = holding.shares / len(lots_sorted)
            raw_values = [shares_per_lot * lot.price_usd for lot in lots_sorted]
            raw_total = sum(raw_values)
            target = holding.acquisition_value
            scale = (target / raw_total) if raw_total > 0 else 1.0

            for lot, raw_value in zip(lots_sorted, raw_values, strict=False):
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
        self, records: list[PurchaseRecord] | None = None
    ) -> list[SymbolAcquisitionSplit]:
        items = records if records is not None else self.list_purchases(portfolio_only=True)
        holdings = {h.symbol: h for h in self.portfolio.list_open_holdings()}
        estimates = self.build_estimated_lots(items, include_closed=False)

        value_by_symbol: dict[str, float] = defaultdict(float)
        lots_by_symbol: dict[str, int] = defaultdict(int)
        for lot in estimates:
            value_by_symbol[lot.symbol] += lot.estimated_value_usd
            lots_by_symbol[lot.symbol] += 1

        total_value = sum(value_by_symbol.values())
        total_lots = sum(lots_by_symbol.values())

        splits: list[SymbolAcquisitionSplit] = []
        for symbol in sorted(value_by_symbol, key=lambda x: value_by_symbol[x], reverse=True):
            holding = holdings.get(symbol)
            if holding is None:
                continue
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
        self, records: list[PurchaseRecord] | None = None
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

    def lot_estimates_dataframe(self, records: list[PurchaseRecord] | None = None) -> pd.DataFrame:
        estimates = self.build_estimated_lots(records)
        return pd.DataFrame(
            [
                {
                    "Date": lot.label,
                    "Ticker": lot.symbol,
                    "Shares": lot.estimated_shares,
                    "Price $": lot.price_usd,
                    "Est. value $": lot.estimated_value_usd,
                }
                for lot in estimates
            ]
        )

    def create_acquisition_value_treemap(self, records: list[PurchaseRecord] | None = None) -> Any:
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
            title="Acquisition Value by Holding",
            height=480,
            margin={"t": 60, "b": 20},
        )
        return style_figure(fig)

    def create_lots_count_pie(self, records: list[PurchaseRecord] | None = None) -> Any:
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
            title="Purchase Count by Holding",
            height=420,
            margin={"t": 60, "b": 20},
        )
        return style_figure(fig)

    def create_value_vs_lots_chart(self, records: list[PurchaseRecord] | None = None) -> Any:
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
                marker={
                    "size": [max(12, min(50, s.total_shares / 2)) for s in splits],
                    "color": [s.portfolio_weight_pct for s in splits],
                    "colorscale": "Blues",
                    "showscale": True,
                    "colorbar": {"title": "% value"},
                },
                customdata=[
                    [s.symbol, s.lot_count, s.total_shares, s.db_acquisition_usd] for s in splits
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
            title="Purchases vs Estimated Acquisition Value",
            xaxis_title="Number of Purchases",
            yaxis_title="Estimated Acquisition Value (USD)",
            height=480,
            margin={"t": 60, "b": 40},
        )
        return style_figure(fig)

    def create_dual_split_bar(self, records: list[PurchaseRecord] | None = None) -> Any:
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
                name="Acquisition Value (USD)",
                x=tickers,
                y=[s.journal_acquisition_usd for s in top],
                marker_color=PALETTE["deposit"],
                yaxis="y",
                offsetgroup=0,
                hovertemplate="%{x}<br>$%{y:,.0f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Bar(
                name="# Purchases",
                x=tickers,
                y=[s.lot_count for s in top],
                marker_color=PALETTE["primary_light"],
                yaxis="y2",
                offsetgroup=1,
                hovertemplate="%{x}<br>%{y} trades<extra></extra>",
            )
        )
        fig.update_layout(
            title="Top 20 Holdings — Acquisition Value vs. Purchase Count",
            barmode="group",
            yaxis={"title": "Acquisition Value (USD)"},
            yaxis2={"title": "Number of Purchases", "overlaying": "y", "side": "right"},
            height=440,
            margin={"t": 60, "b": 80},
            xaxis={"tickangle": -45, "automargin": True},
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        )
        return style_figure(fig)

    def create_timeline_chart(self, records: list[PurchaseRecord] | None = None) -> Any:
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
                marker={"size": 9, "color": "#1976d2"},
                customdata=[[item.symbol, item.label, item.price_usd] for item in items],
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[1]}<br>"
                    "$%{customdata[2]:.2f}<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            title="Purchase Journal — Timeline",
            xaxis_title="Date",
            yaxis={
                "tickmode": "array",
                "tickvals": list(symbol_y.values()),
                "ticktext": symbols,
            },
            height=max(420, 22 * len(symbols)),
            margin={"t": 60, "b": 40, "l": 80},
        )
        return style_figure(fig)

    def create_yearly_activity_chart(self, records: list[PurchaseRecord] | None = None) -> Any:
        if not PLOTLY_AVAILABLE:
            return None
        yearly = self.yearly_counts(records)
        if yearly.empty:
            return None
        fig = go.Figure(
            go.Bar(
                x=yearly["Year"].astype(str),
                y=yearly["Purchases"],
                marker_color=PALETTE["primary"],
                hovertemplate="%{x}<br>%{y} purchases<extra></extra>",
            )
        )
        fig.update_layout(
            title="Purchases per Year",
            yaxis_title="Number of Transactions",
            height=340,
            margin={"t": 60, "b": 40},
        )
        return style_figure(fig)

    def create_price_scatter_by_symbol(self, records: list[PurchaseRecord] | None = None) -> Any:
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
            title="Purchase Price Over Time by Ticker",
            xaxis_title="Date",
            yaxis_title="Purchase Price (USD)",
            height=440,
            margin={"t": 60, "b": 60},
            legend=bottom_legend(),
        )
        return style_figure(fig)
