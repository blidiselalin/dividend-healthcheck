"""Tests for purchase journal shares and commission fields."""

from __future__ import annotations

from datetime import date

from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService


def test_add_purchase_stores_shares_and_commission(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("KO", shares=10.0, avg_cost_per_share=50.0)
    record = journal_store.add_purchase(
        "KO",
        date(2024, 3, 1),
        52.0,
        shares=4.0,
        commission_usd=2.5,
    )
    assert record.shares == 4.0
    assert record.commission_usd == 2.5
    assert record.lot_cost_usd == 210.5

    loaded = journal_store.list_purchases()
    assert len(loaded) == 1
    assert loaded[0].shares == 4.0
    assert loaded[0].commission_usd == 2.5


def test_build_estimated_lots_uses_recorded_shares(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("KO", shares=15.0, avg_cost_per_share=50.0)
    journal_store.add_purchase("KO", date(2024, 1, 1), 48.0, shares=10.0, commission_usd=0.0)
    journal_store.add_purchase("KO", date(2024, 6, 1), 52.0, shares=5.0, commission_usd=1.0)

    service = PortfolioPurchaseJournalService(
        journal_store=journal_store,
        portfolio_store=portfolio_store,
    )
    lots = service.build_estimated_lots()
    assert len(lots) == 2
    assert lots[0].estimated_shares == 10.0
    assert lots[0].estimated_value_usd == 480.0
    assert lots[1].estimated_shares == 5.0
    assert lots[1].estimated_value_usd == 261.0
