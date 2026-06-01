"""
Wire portfolio stores to a single database path (Postgres user scope or SQLite file).

Always use this when a service touches holdings + journal + dividends together.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from data_ingestion.deposits_store import DepositsStore
from data_ingestion.dividend_income_store import DividendIncomeStore
from data_ingestion.dividend_receipt_store import DividendReceiptStore
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_holding_detail_service import PortfolioHoldingDetailService
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService


@dataclass(frozen=True)
class PortfolioContext:
    db_path: Path
    portfolio: PortfolioStore
    journal: PurchaseJournalStore
    deposits: DepositsStore
    dividends: DividendIncomeStore
    receipts: DividendReceiptStore
    detail: PortfolioHoldingDetailService
    journal_service: PortfolioPurchaseJournalService


def create_portfolio_context(db_path: Optional[Path] = None) -> PortfolioContext:
    """Create portfolio stores that share one ``db_path`` / Postgres user scope."""
    portfolio = PortfolioStore(db_path=db_path, seed=False)
    path = portfolio.db_path
    journal = PurchaseJournalStore(db_path=path, seed=False)
    deposits = DepositsStore(db_path=path, seed=False)
    dividends = DividendIncomeStore(db_path=path, seed=False)
    receipts = DividendReceiptStore(db_path=path)
    journal_service = PortfolioPurchaseJournalService(
        journal_store=journal,
        portfolio_store=portfolio,
    )
    detail = PortfolioHoldingDetailService(
        journal=journal_service,
        portfolio=portfolio,
        receipts=receipts,
    )
    return PortfolioContext(
        db_path=path,
        portfolio=portfolio,
        journal=journal,
        deposits=deposits,
        dividends=dividends,
        receipts=receipts,
        detail=detail,
        journal_service=journal_service,
    )
