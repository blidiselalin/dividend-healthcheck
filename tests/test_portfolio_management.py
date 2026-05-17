"""Tests for portfolio CRUD and management service."""

from __future__ import annotations

from datetime import date

import pytest

from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_management_service import PortfolioManagementService


def test_upsert_and_update_holding(portfolio_store: PortfolioStore) -> None:
    holding = portfolio_store.upsert_holding(
        "TEST",
        shares=10,
        avg_cost_per_share=50.0,
        company_name="Test Corp",
    )
    assert holding.symbol == "TEST"
    assert holding.shares == 10
    assert holding.acquisition_value == 500.0
    assert holding.company_name == "Test Corp"

    updated = portfolio_store.update_holding("TEST", shares=15)
    assert updated is not None
    assert updated.shares == 15
    assert updated.acquisition_value == 750.0

    assert portfolio_store.delete_holding("TEST")
    assert portfolio_store.get_holding("TEST") is None


def test_add_ticker_skips_validation(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    result = service.add_ticker(
        "XYZ",
        shares=5,
        avg_cost_per_share=12.5,
        skip_validation=True,
        enrich_vector=False,
    )
    assert result["symbol"] == "XYZ"
    assert portfolio_store.holding_exists("XYZ")


def test_add_ticker_duplicate_raises(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    service.add_ticker(
        "DUP",
        shares=1,
        avg_cost_per_share=10.0,
        skip_validation=True,
        enrich_vector=False,
    )
    with pytest.raises(ValueError, match="already"):
        service.add_ticker(
            "dup",
            shares=2,
            avg_cost_per_share=11.0,
            skip_validation=True,
            enrich_vector=False,
        )


def test_validate_symbol_rejects_delisted(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    result = service.validate_symbol("WBA")
    assert not result.valid
    assert "delisted" in result.message.lower()


def test_validate_symbol_rejects_bad_format(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    result = service.validate_symbol("###")
    assert not result.valid


def test_add_purchase_requires_holding(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store, journal=journal_store)
    with pytest.raises(ValueError, match="holdings"):
        service.add_purchase("NOPE", date(2024, 1, 15), 10.5)

    service.add_ticker(
        "AAA",
        shares=1,
        avg_cost_per_share=1.0,
        skip_validation=True,
        enrich_vector=False,
    )
    record = service.add_purchase("AAA", date(2024, 1, 15), 10.5)
    assert record.symbol == "AAA"
    assert record.price_usd == 10.5


def test_add_deposit(
    portfolio_store: PortfolioStore,
    deposits_store,
) -> None:
    service = PortfolioManagementService(
        portfolio=portfolio_store,
        deposits=deposits_store,
    )
    dep = service.add_deposit(
        year=2026,
        month=5,
        label="May 2026",
        deposit_eur=100.0,
        deposit_usd=110.0,
        portfolio_eur=120000.0,
    )
    assert dep.period_key == "2026-05"
    assert dep.portfolio_eur == 120000.0


def test_remove_ticker(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    service.add_ticker(
        "RM",
        shares=3,
        avg_cost_per_share=5.0,
        skip_validation=True,
        enrich_vector=False,
    )
    assert service.remove_ticker("RM")
    assert not portfolio_store.holding_exists("RM")
