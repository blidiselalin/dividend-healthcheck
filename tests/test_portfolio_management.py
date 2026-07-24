"""Tests for portfolio CRUD and management service."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from data_ingestion.deposits_store import DepositsStore, MonthlyDeposit
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
    record = service.add_purchase("AAA", date(2024, 1, 15), 10.5, shares=5.0, commission_usd=1.0)
    assert record.symbol == "AAA"
    assert record.price_usd == 10.5
    assert record.shares == 5.0
    assert record.commission_usd == 1.0
    holding = portfolio_store.get_holding("AAA")
    assert holding is not None
    assert holding.shares == 6.0
    assert holding.commission == 1.0


def test_add_deposit(
    portfolio_store: PortfolioStore,
    deposits_store: DepositsStore,
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


def test_get_deposit_and_missing_portfolio(
    portfolio_store: PortfolioStore,
    deposits_store: DepositsStore,
) -> None:
    service = PortfolioManagementService(
        portfolio=portfolio_store,
        deposits=deposits_store,
    )
    service.add_deposit(
        year=2026,
        month=4,
        label="April 2026",
        deposit_eur=0.0,
        deposit_usd=0.0,
        portfolio_eur=117565.63,
    )
    service.add_deposit(
        year=2026,
        month=5,
        label="May 2026",
        deposit_eur=4111.6,
        deposit_usd=4821.01,
        portfolio_eur=0.0,
    )

    may = service.get_deposit(2026, 5)
    assert may is not None
    assert may.deposit_eur == 4111.6
    assert may.portfolio_eur == 0.0
    assert service.get_deposit(2026, 6) is None

    missing = service.deposits_missing_portfolio_value()
    assert len(missing) == 1
    assert missing[0].period_key == "2026-05"


def test_estimate_portfolio_eur_from_usd_uses_deposit_fx() -> None:
    deposit = MonthlyDeposit(
        period=date(2026, 5, 1),
        label="May 2026",
        deposit_eur=4111.6,
        deposit_usd=4821.01,
        portfolio_eur=0.0,
        sort_order=1,
    )
    with patch(
        "services.fx_rate_service.load_eur_usd_market_series",
        return_value=[],
    ):
        estimated = PortfolioManagementService.estimate_portfolio_eur_from_usd(
            100_000.0,
            deposit,
            as_of=date(2026, 5, 31),
        )
    expected = round(100_000.0 * (4111.6 / 4821.01), 2)
    assert estimated == expected


def test_estimate_portfolio_eur_from_usd_default_fx() -> None:
    with patch(
        "services.fx_rate_service.load_eur_usd_market_series",
        return_value=[],
    ):
        estimated = PortfolioManagementService.estimate_portfolio_eur_from_usd(1000.0)
    assert estimated == 920.0


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


# ---------------------------------------------------------------------------
# normalize_symbol
# ---------------------------------------------------------------------------


def test_normalize_symbol_uppercases_and_strips() -> None:
    assert PortfolioManagementService.normalize_symbol(" ko ") == "KO"
    assert PortfolioManagementService.normalize_symbol("brk.b") == "BRK.B"
    assert PortfolioManagementService.normalize_symbol("  xyz  ") == "XYZ"


# ---------------------------------------------------------------------------
# validate_symbol — edge cases
# ---------------------------------------------------------------------------


def test_validate_symbol_empty_string_returns_invalid(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    result = service.validate_symbol("")
    assert not result.valid
    assert result.message


def test_validate_symbol_rejects_whitespace_only(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    result = service.validate_symbol("   ")
    assert not result.valid


# ---------------------------------------------------------------------------
# add_ticker — commission and company_name persistence (Add ticker tab)
# ---------------------------------------------------------------------------


def test_add_ticker_stores_commission_and_company_name(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    service.add_ticker(
        "TST",
        shares=10,
        avg_cost_per_share=50.0,
        commission=9.99,
        company_name="Test Corp",
        skip_validation=True,
        enrich_vector=False,
    )
    holding = portfolio_store.get_holding("TST")
    assert holding is not None
    assert holding.commission == 9.99
    assert holding.company_name == "Test Corp"


def test_add_ticker_normalizes_lowercase_input(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    service.add_ticker(
        " ko ",
        shares=5,
        avg_cost_per_share=60.0,
        skip_validation=True,
        enrich_vector=False,
    )
    holding = portfolio_store.get_holding("KO")
    assert holding is not None
    assert holding.symbol == "KO"


# ---------------------------------------------------------------------------
# update_holding_fields — Edit position tab
# ---------------------------------------------------------------------------


def test_update_holding_fields_updates_commission_and_company_name(
    portfolio_store: PortfolioStore,
) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    service.add_ticker(
        "UPD",
        shares=5,
        avg_cost_per_share=20.0,
        skip_validation=True,
        enrich_vector=False,
    )
    updated = service.update_holding_fields(
        "UPD",
        commission=7.50,
        company_name="Updated Corp",
    )
    assert updated is not None
    assert updated.commission == 7.50
    assert updated.company_name == "Updated Corp"


def test_update_holding_fields_returns_none_for_missing_symbol(
    portfolio_store: PortfolioStore,
) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    result = service.update_holding_fields("NOPE", shares=1.0)
    assert result is None


def test_update_holding_fields_preserves_unspecified_fields(
    portfolio_store: PortfolioStore,
) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    service.add_ticker(
        "PRV",
        shares=10,
        avg_cost_per_share=30.0,
        commission=5.0,
        company_name="Preserve Corp",
        skip_validation=True,
        enrich_vector=False,
    )
    updated = service.update_holding_fields("PRV", shares=15.0)
    assert updated is not None
    assert updated.shares == 15.0
    assert updated.commission == 5.0
    assert updated.company_name == "Preserve Corp"


# ---------------------------------------------------------------------------
# add_purchase — Purchase tab validation
# ---------------------------------------------------------------------------


def test_add_purchase_rejects_zero_price(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store, journal=journal_store)
    service.add_ticker(
        "ZPR",
        shares=1,
        avg_cost_per_share=10.0,
        skip_validation=True,
        enrich_vector=False,
    )
    with pytest.raises(ValueError, match="[Pp]rice"):
        service.add_purchase("ZPR", date(2024, 6, 1), 0.0)


def test_add_purchase_rejects_negative_price(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store, journal=journal_store)
    service.add_ticker(
        "NPR",
        shares=1,
        avg_cost_per_share=10.0,
        skip_validation=True,
        enrich_vector=False,
    )
    with pytest.raises(ValueError, match="[Pp]rice"):
        service.add_purchase("NPR", date(2024, 6, 1), -5.0)


# ---------------------------------------------------------------------------
# list_holdings / list_deposits — service wrappers
# ---------------------------------------------------------------------------


def test_list_holdings_via_service(portfolio_store: PortfolioStore) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store)
    assert service.list_holdings() == []
    service.add_ticker(
        "LS1",
        shares=5,
        avg_cost_per_share=10.0,
        skip_validation=True,
        enrich_vector=False,
    )
    service.add_ticker(
        "LS2",
        shares=3,
        avg_cost_per_share=20.0,
        skip_validation=True,
        enrich_vector=False,
    )
    holdings = service.list_holdings()
    assert len(holdings) == 2
    assert {h.symbol for h in holdings} == {"LS1", "LS2"}


def test_list_deposits_via_service(
    portfolio_store: PortfolioStore,
    deposits_store: DepositsStore,
) -> None:
    service = PortfolioManagementService(portfolio=portfolio_store, deposits=deposits_store)
    assert service.list_deposits() == []
    service.add_deposit(
        year=2025,
        month=1,
        label="January 2025",
        deposit_eur=1000.0,
        deposit_usd=1100.0,
        portfolio_eur=50000.0,
    )
    deposits = service.list_deposits()
    assert len(deposits) == 1
    assert deposits[0].period_key == "2025-01"
    assert deposits[0].deposit_eur == 1000.0
