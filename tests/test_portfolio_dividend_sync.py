"""Tests for automatic dividend receipt tracking."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from data_ingestion.models import DividendRecord, StockDocument
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_dividend_sync_service import sync_received_dividends


def _doc_with_dividends() -> StockDocument:
    return StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(
                ex_date=date(2024, 3, 14),
                payment_date=date(2024, 4, 1),
                amount=0.46,
            ),
            DividendRecord(
                ex_date=date(2024, 6, 14),
                payment_date=date(2024, 7, 1),
                amount=0.48,
            ),
        ],
    )


def test_sync_records_paid_dividends_and_updates_holding(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    journal = PurchaseJournalStore(db_path=db, seed=False)
    portfolio.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)
    journal.add_purchase("KO", date(2024, 1, 1), 48.0)

    with patch(
        "services.portfolio_dividend_sync_service._load_documents",
        return_value={"KO": _doc_with_dividends()},
    ):
        stats = sync_received_dividends(db_path=db)

    assert stats.receipts_added == 2
    holding = portfolio.get_holding("KO")
    assert holding is not None
    assert holding.dividends_paid == pytest.approx(9.80, rel=0.01)


def test_sync_respects_purchase_journal_shares(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    journal = PurchaseJournalStore(db_path=db, seed=False)
    portfolio.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)
    journal.add_purchase("KO", date(2024, 5, 1), 52.0)

    with patch(
        "services.portfolio_dividend_sync_service._load_documents",
        return_value={"KO": _doc_with_dividends()},
    ):
        stats = sync_received_dividends(db_path=db)

    assert stats.receipts_added == 1
    holding = portfolio.get_holding("KO")
    assert holding is not None
    assert holding.dividends_paid == pytest.approx(4.62, rel=0.01)


def test_drop_holding_keeps_dividend_receipts(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    portfolio.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)
    from data_ingestion.dividend_receipt_store import DividendReceiptStore

    DividendReceiptStore(db_path=db).sync_receipt(
        "KO",
        ex_date=date(2024, 4, 1),
        pay_date=date(2024, 4, 1),
        per_share_usd=0.46,
        shares_held=10.0,
        gross_usd=4.60,
        source="ibkr",
    )

    assert portfolio.drop_holding("KO") is True

    assert portfolio.get_holding("KO") is None
    assert len(DividendReceiptStore(db_path=db).list_for_symbol("KO")) == 1


def test_delete_holding_removes_dividend_receipts(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    portfolio.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)

    with patch(
        "services.portfolio_dividend_sync_service._load_documents",
        return_value={"KO": _doc_with_dividends()},
    ):
        sync_received_dividends(db_path=db)

    assert portfolio.delete_holding("KO") is True
    from data_ingestion.dividend_receipt_store import DividendReceiptStore

    assert DividendReceiptStore(db_path=db).list_for_symbol("KO") == []


def test_tracking_since_limits_history_without_journal(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    portfolio.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)

    with patch(
        "services.portfolio_dividend_sync_service._load_documents",
        return_value={"KO": _doc_with_dividends()},
    ):
        stats = sync_received_dividends(db_path=db)

    # Only dividends on/after tracking start (today) — historical rows skipped.
    assert stats.receipts_added == 0
