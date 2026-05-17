"""Tests for portfolio ↔ vector DB linkage."""

from __future__ import annotations

from datetime import date

import pytest

from data_ingestion.models import StockDocument
from data_ingestion.portfolio_store import PortfolioHolding, PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services import portfolio_vector_sync as sync


def test_apply_portfolio_fields_sets_metadata() -> None:
    doc = StockDocument(symbol="KO", name="KO")
    holding = PortfolioHolding(
        symbol="KO",
        shares=20.0,
        avg_cost_per_share=58.58,
        acquisition_value=1171.6,
        commission=1.05,
        dividends_paid=113.2,
        estimated_avg_price=79.52,
        sort_order=23,
    )
    sync.apply_portfolio_fields(
        doc,
        holding=holding,
        purchase_count=3,
        company_name="Coca-Cola Co",
    )
    assert doc.in_portfolio is True
    assert doc.name == "Coca-Cola Co"
    assert doc.portfolio_shares == 20.0
    assert doc.portfolio_purchase_count == 3
    assert "Portfolio holding" in doc.embedding_text


def test_company_name_for_prefers_holding_db(
    portfolio_store: PortfolioStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio_store.upsert_holding(
        "NEW",
        shares=1,
        avg_cost_per_share=10.0,
        company_name="Custom Name Inc",
    )
    monkeypatch.setattr(sync, "PortfolioStore", lambda db_path=None: portfolio_store)
    assert sync._company_name_for("NEW") == "Custom Name Inc"


def test_collect_portfolio_symbols(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _portfolio_store(db_path=None, seed=True):
        return portfolio_store

    def _journal_store(db_path=None, seed=True):
        return journal_store

    monkeypatch.setattr(sync, "PortfolioStore", _portfolio_store)
    monkeypatch.setattr(sync, "PurchaseJournalStore", _journal_store)

    portfolio_store.upsert_holding("AAA", shares=1, avg_cost_per_share=1.0)
    journal_store.add_purchase("BBB", date(2024, 1, 1), 5.0)

    symbols = sync.collect_portfolio_symbols()
    assert symbols == {"AAA", "BBB"}


def test_collect_portfolio_symbols_excludes_delisted(
    portfolio_store: PortfolioStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync, "PortfolioStore", lambda db_path=None: portfolio_store)
    monkeypatch.setattr(
        sync,
        "PurchaseJournalStore",
        lambda db_path=None: PurchaseJournalStore(db_path=portfolio_store.db_path),
    )
    portfolio_store.upsert_holding("WBA", shares=1, avg_cost_per_share=1.0)
    assert "WBA" not in sync.collect_portfolio_symbols()
