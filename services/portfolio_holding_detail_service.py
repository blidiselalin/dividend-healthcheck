"""
Per-holding purchase and dividend cash history for the Holdings drill-down panel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, TYPE_CHECKING, Any

import pandas as pd

from data_ingestion.portfolio_store import PortfolioStore
from services.portfolio_purchase_journal_service import (
    EstimatedPurchaseLot,
    PortfolioPurchaseJournalService,
)

if TYPE_CHECKING:
    from data_ingestion.models import DividendRecord, StockDocument


def _cash_date(record: "DividendRecord") -> date:
    if record.payment_date:
        return record.payment_date
    return record.ex_date + timedelta(days=14)


def shares_as_of(
    lots: List[EstimatedPurchaseLot],
    as_of: date,
    *,
    fallback_shares: float,
) -> float:
    """Shares owned on or before the given date (from journal lots)."""
    if not lots:
        return fallback_shares
    owned = sum(
        lot.estimated_shares
        for lot in lots
        if lot.purchase_date <= as_of
    )
    return owned if owned > 0 else 0.0


@dataclass(frozen=True)
class HoldingPurchaseRow:
    purchase_date: date
    label: str
    price_usd: float
    estimated_shares: float
    estimated_cost_usd: float
    cumulative_shares: float


@dataclass(frozen=True)
class HoldingDividendRow:
    ex_date: date
    pay_date: date
    per_share_usd: float
    shares_held: float
    cash_usd: float


@dataclass(frozen=True)
class HoldingDetailSummary:
    symbol: str
    purchase_count: int
    total_estimated_cost_usd: float
    dividend_payment_count: int
    total_dividend_cash_usd: float
    uses_journal_shares: bool


class PortfolioHoldingDetailService:
    """Build purchase and dividend histories for one portfolio symbol."""

    def __init__(
        self,
        journal: Optional[PortfolioPurchaseJournalService] = None,
        portfolio: Optional[PortfolioStore] = None,
        receipts: Optional[Any] = None,
    ) -> None:
        if journal is None and portfolio is None and receipts is None:
            from services.portfolio_context import create_portfolio_context

            ctx = create_portfolio_context()
            self.journal = ctx.journal_service
            self.portfolio = ctx.portfolio
            self._receipts = ctx.receipts
        else:
            self.journal = journal or PortfolioPurchaseJournalService()
            self.portfolio = portfolio or PortfolioStore(seed=False)
            self._receipts = receipts

    def _receipt_store(self):
        if self._receipts is not None:
            return self._receipts
        from data_ingestion.dividend_receipt_store import DividendReceiptStore

        return DividendReceiptStore(db_path=self.portfolio.db_path)

    def estimated_lots_for_symbol(self, symbol: str) -> List[EstimatedPurchaseLot]:
        return [
            lot
            for lot in self.journal.build_estimated_lots()
            if lot.symbol == symbol
        ]

    def purchase_history(self, symbol: str) -> List[HoldingPurchaseRow]:
        lots = sorted(
            self.estimated_lots_for_symbol(symbol),
            key=lambda lot: lot.purchase_date,
        )
        cumulative = 0.0
        rows: List[HoldingPurchaseRow] = []
        for lot in lots:
            cumulative += lot.estimated_shares
            rows.append(
                HoldingPurchaseRow(
                    purchase_date=lot.purchase_date,
                    label=lot.label,
                    price_usd=lot.price_usd,
                    estimated_shares=lot.estimated_shares,
                    estimated_cost_usd=lot.estimated_value_usd,
                    cumulative_shares=round(cumulative, 4),
                )
            )
        return rows

    def stored_dividend_history(self, symbol: str) -> List[HoldingDividendRow]:
        receipts = self._receipt_store().list_for_symbol(symbol)
        return [
            HoldingDividendRow(
                ex_date=receipt.ex_date,
                pay_date=receipt.pay_date,
                per_share_usd=receipt.per_share_usd,
                shares_held=receipt.shares_held,
                cash_usd=receipt.gross_usd,
            )
            for receipt in receipts
        ]

    def dividend_history(
        self,
        symbol: str,
        document: Optional["StockDocument"],
        *,
        current_shares: float,
        tracking_since: Optional[date] = None,
        prefer_stored: bool = False,
    ) -> List[HoldingDividendRow]:
        if prefer_stored:
            stored = self.stored_dividend_history(symbol)
            if stored:
                return stored

        if not document or not document.dividend_history:
            return []

        lots = self.estimated_lots_for_symbol(symbol)
        fallback = current_shares if not lots else 0.0

        rows: List[HoldingDividendRow] = []
        for record in sorted(document.dividend_history, key=lambda r: r.ex_date):
            if not lots and tracking_since and record.ex_date < tracking_since:
                continue
            pay = _cash_date(record)
            held = shares_as_of(lots, record.ex_date, fallback_shares=fallback)
            if held <= 0:
                continue
            cash = round(held * float(record.amount), 2)
            rows.append(
                HoldingDividendRow(
                    ex_date=record.ex_date,
                    pay_date=pay,
                    per_share_usd=float(record.amount),
                    shares_held=round(held, 4),
                    cash_usd=cash,
                )
            )
        return rows

    def summarize(
        self,
        symbol: str,
        document: Optional["StockDocument"],
        *,
        current_shares: float,
        tracking_since: Optional[date] = None,
    ) -> HoldingDetailSummary:
        purchases = self.purchase_history(symbol)
        dividends = self.dividend_history(
            symbol, document, current_shares=current_shares, tracking_since=tracking_since
        )
        return HoldingDetailSummary(
            symbol=symbol,
            purchase_count=len(purchases),
            total_estimated_cost_usd=round(
                sum(row.estimated_cost_usd for row in purchases), 2
            ),
            dividend_payment_count=len(dividends),
            total_dividend_cash_usd=round(
                sum(row.cash_usd for row in dividends), 2
            ),
            uses_journal_shares=bool(purchases),
        )

    def purchases_dataframe(self, symbol: str) -> pd.DataFrame:
        rows = self.purchase_history(symbol)
        if not rows:
            return pd.DataFrame(
                columns=[
                    "Date",
                    "Price $",
                    "Est. shares",
                    "Est. cost $",
                    "Cumulative shares",
                ]
            )
        return pd.DataFrame(
            [
                {
                    "Date": row.label,
                    "Price $": row.price_usd,
                    "Est. shares": row.estimated_shares,
                    "Est. cost $": row.estimated_cost_usd,
                    "Cumulative shares": row.cumulative_shares,
                }
                for row in rows
            ]
        )

    def dividends_dataframe(
        self,
        symbol: str,
        document: Optional["StockDocument"],
        *,
        current_shares: float,
        tracking_since: Optional[date] = None,
    ) -> pd.DataFrame:
        rows = self.dividend_history(
            symbol,
            document,
            current_shares=current_shares,
            tracking_since=tracking_since,
            prefer_stored=True,
        )
        if not rows:
            return pd.DataFrame(
                columns=[
                    "Ex-date",
                    "Pay date",
                    "$/share",
                    "Shares held",
                    "Cash $",
                ]
            )
        return pd.DataFrame(
            [
                {
                    "Ex-date": row.ex_date,
                    "Pay date": row.pay_date,
                    "$/share": row.per_share_usd,
                    "Shares held": row.shares_held,
                    "Cash $": row.cash_usd,
                }
                for row in rows
            ]
        )
