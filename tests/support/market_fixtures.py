"""Shared fixtures for market-data provider tests."""

from __future__ import annotations

from data_ingestion.deposits_store import DepositsStore
from data_ingestion.dividend_income_store import DividendIncomeStore
from data_ingestion.dividend_receipt_store import DividendReceiptStore
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_context import PortfolioContext
from services.portfolio_holding_detail_service import PortfolioHoldingDetailService
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService


def portfolio_context_from_stores(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> PortfolioContext:
    """Build a full ``PortfolioContext`` for isolated SQLite tests."""
    return PortfolioContext(
        db_path=portfolio_store.db_path,
        portfolio=portfolio_store,
        journal=journal_store,
        deposits=DepositsStore(db_path=portfolio_store.db_path, seed=False),
        dividends=DividendIncomeStore(db_path=portfolio_store.db_path, seed=False),
        receipts=DividendReceiptStore(db_path=portfolio_store.db_path),
        detail=PortfolioHoldingDetailService(
            journal=PortfolioPurchaseJournalService(
                journal_store=journal_store,
                portfolio_store=portfolio_store,
            ),
            portfolio=portfolio_store,
            receipts=DividendReceiptStore(db_path=portfolio_store.db_path),
        ),
        journal_service=PortfolioPurchaseJournalService(
            journal_store=journal_store,
            portfolio_store=portfolio_store,
        ),
    )
