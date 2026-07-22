"""Unit tests for SQLite portfolio, journal, and deposits stores."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date

import pytest

from data_ingestion.deposits_store import DepositsStore
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import (
    PurchaseJournalStore,
    portfolio_symbols,
)


def test_portfolio_upsert_rejects_invalid_shares(
    portfolio_store: PortfolioStore,
) -> None:
    with pytest.raises(ValueError, match="Shares"):
        portfolio_store.upsert_holding("X", shares=0, avg_cost_per_share=10.0)


def test_portfolio_upsert_rejects_empty_symbol(portfolio_store: PortfolioStore) -> None:
    with pytest.raises(ValueError, match="Symbol"):
        portfolio_store.upsert_holding("", shares=1, avg_cost_per_share=1.0)


def test_portfolio_symbols_follows_holdings(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("AAA", shares=5, avg_cost_per_share=10.0)
    journal_store.add_purchase("BBB", date(2024, 1, 1), 12.0)
    assert portfolio_symbols(portfolio_store.db_path) == {"AAA"}


def test_journal_add_purchase_idempotent(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("ZZ", shares=1, avg_cost_per_share=1.0)
    first = journal_store.add_purchase("ZZ", date(2024, 3, 1), 25.0)
    second = journal_store.add_purchase("ZZ", date(2024, 3, 1), 25.0)
    assert first.id == second.id
    assert len(journal_store.list_purchases(portfolio_only=False)) == 1


def test_journal_list_portfolio_only(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("IN", shares=1, avg_cost_per_share=1.0)
    journal_store.add_purchase("IN", date(2024, 1, 1), 1.0)
    journal_store.add_purchase("OUT", date(2024, 1, 2), 2.0)
    portfolio_only = journal_store.list_purchases(portfolio_only=True)
    assert [p.symbol for p in portfolio_only] == ["IN"]


def test_journal_delete_purchase(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("DEL", shares=1, avg_cost_per_share=1.0)
    record = journal_store.add_purchase("DEL", date(2024, 5, 1), 9.0)
    assert record.id is not None
    assert journal_store.delete_purchase(record.id)
    assert journal_store.list_purchases(portfolio_only=False) == []


def test_portfolio_upsert_rejects_negative_avg_cost(portfolio_store: PortfolioStore) -> None:
    with pytest.raises(ValueError, match="[Cc]ost"):
        portfolio_store.upsert_holding("X", shares=1, avg_cost_per_share=-1.0)


def test_portfolio_update_holding_returns_none_for_missing(
    portfolio_store: PortfolioStore,
) -> None:
    result = portfolio_store.update_holding("MISSING", shares=5)
    assert result is None


def test_drop_holding_removes_row_but_not_journal(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("SOLD", shares=5, avg_cost_per_share=20.0)
    journal_store.add_purchase(
        "SOLD",
        date(2024, 1, 1),
        20.0,
        shares=5.0,
        side="sell",
        source="ibkr",
    )
    assert portfolio_store.drop_holding("SOLD") is True
    assert portfolio_store.get_holding("SOLD") is None
    assert len(journal_store.list_purchases(portfolio_only=False)) == 1


def test_portfolio_set_dividends_paid(portfolio_store: PortfolioStore) -> None:
    portfolio_store.upsert_holding("DIV", shares=10, avg_cost_per_share=50.0)
    portfolio_store.set_dividends_paid("DIV", 123.45)
    holding = portfolio_store.get_holding("DIV")
    assert holding is not None
    assert holding.dividends_paid == 123.45


def test_journal_add_purchase_rejects_zero_price(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("ZP", shares=1, avg_cost_per_share=1.0)
    with pytest.raises(ValueError, match="[Pp]rice"):
        journal_store.add_purchase("ZP", date(2024, 1, 1), 0.0)


def test_journal_add_purchase_rejects_negative_price(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("NP", shares=1, avg_cost_per_share=1.0)
    with pytest.raises(ValueError, match="[Pp]rice"):
        journal_store.add_purchase("NP", date(2024, 1, 1), -10.0)


def test_deposits_upsert_and_delete(deposits_store: DepositsStore) -> None:
    dep = deposits_store.upsert_deposit(
        year=2025,
        month=6,
        label="June 2025",
        deposit_eur=100.0,
        deposit_usd=110.0,
        portfolio_eur=5000.0,
    )
    assert dep.period_key == "2025-06"
    assert dep.deposit_eur == 100.0

    updated = deposits_store.upsert_deposit(
        year=2025,
        month=6,
        label="June 2025 (revised)",
        deposit_eur=150.0,
        deposit_usd=165.0,
        portfolio_eur=5100.0,
    )
    assert updated.deposit_eur == 150.0
    assert len(deposits_store.list_deposits()) == 1

    assert deposits_store.delete_deposit("2025-06")
    assert deposits_store.list_deposits() == []
