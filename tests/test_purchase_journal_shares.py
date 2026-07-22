"""Tests for purchase journal shares and commission fields."""

from __future__ import annotations

from datetime import date

import pytest

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


def test_sell_lot_cost_is_negative(journal_store: PurchaseJournalStore) -> None:
    record = journal_store.add_purchase(
        "KO",
        date(2024, 8, 1),
        55.0,
        shares=4.0,
        commission_usd=1.0,
        side="sell",
        source="ibkr",
    )
    assert record.lot_cost_usd == -221.0


def test_build_estimated_lots_includes_sold_symbol_without_holding(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("AMCR", shares=20.0, avg_cost_per_share=10.0)
    journal_store.add_purchase(
        "AMCR",
        date(2024, 4, 1),
        10.0,
        shares=20.0,
        side="buy",
        source="ibkr",
    )
    journal_store.add_purchase(
        "AMCR",
        date(2024, 5, 1),
        11.0,
        shares=20.0,
        side="sell",
        source="ibkr",
    )
    portfolio_store.drop_holding("AMCR")

    service = PortfolioPurchaseJournalService(
        journal_store=journal_store,
        portfolio_store=portfolio_store,
    )
    lots = [
        lot for lot in service.build_estimated_lots(include_closed=True) if lot.symbol == "AMCR"
    ]
    assert len(lots) == 2
    assert sum(lot.estimated_shares for lot in lots) == pytest.approx(0.0)


def test_list_purchases_includes_fully_sold_symbol(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    journal_store.add_purchase(
        "AAPL",
        date(2024, 1, 1),
        150.0,
        shares=10.0,
        side="buy",
        source="ibkr",
    )
    journal_store.add_purchase(
        "AAPL",
        date(2024, 8, 1),
        170.0,
        shares=10.0,
        side="sell",
        source="ibkr",
    )

    service = PortfolioPurchaseJournalService(
        journal_store=journal_store,
        portfolio_store=portfolio_store,
    )
    records = service.list_purchases()
    assert len(records) == 2
    assert {record.side for record in records} == {"buy", "sell"}


def test_build_estimated_lots_keeps_sells_when_legacy_buy_lacks_shares(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("KO", shares=5.0, avg_cost_per_share=50.0)
    journal_store.add_purchase("KO", date(2024, 1, 1), 48.0)
    journal_store.add_purchase(
        "KO",
        date(2024, 8, 1),
        55.0,
        shares=5.0,
        side="sell",
        source="ibkr",
    )

    service = PortfolioPurchaseJournalService(
        journal_store=journal_store,
        portfolio_store=portfolio_store,
    )
    lots = service.build_estimated_lots()
    sell_lots = [lot for lot in lots if lot.estimated_shares < 0]
    assert sell_lots
    assert sell_lots[0].estimated_shares == pytest.approx(-5.0)


def test_chronological_dataframe_includes_side(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("KO", shares=10.0, avg_cost_per_share=50.0)
    journal_store.add_purchase("KO", date(2024, 1, 1), 48.0, shares=10.0, side="buy")
    journal_store.add_purchase(
        "KO",
        date(2024, 6, 1),
        52.0,
        shares=3.0,
        side="sell",
        source="ibkr",
    )

    service = PortfolioPurchaseJournalService(
        journal_store=journal_store,
        portfolio_store=portfolio_store,
    )
    frame = service.chronological_dataframe()
    assert "Side" in frame.columns
    assert set(frame["Side"]) == {"Buy", "Sell"}


def test_manual_sell_updates_holding_and_drops_when_flat(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    from services.portfolio_management_service import PortfolioManagementService

    portfolio_store.upsert_holding("KO", shares=10.0, avg_cost_per_share=50.0)
    service = PortfolioManagementService(
        portfolio=portfolio_store,
        journal=journal_store,
    )
    service.add_purchase(
        "KO",
        date(2024, 6, 1),
        55.0,
        shares=10.0,
        commission_usd=1.0,
        side="sell",
    )

    assert portfolio_store.list_open_holdings() == []
    records = journal_store.list_purchases(portfolio_only=False)
    assert len(records) == 1
    assert records[0].side == "sell"
    assert records[0].shares == 10.0

    journal_service = PortfolioPurchaseJournalService(
        journal_store=journal_store,
        portfolio_store=portfolio_store,
    )
    assert journal_service.build_estimated_lots(include_closed=False) == []
    closed_lots = journal_service.build_estimated_lots(include_closed=True)
    assert len(closed_lots) == 1
    assert closed_lots[0].estimated_shares == pytest.approx(-10.0)
