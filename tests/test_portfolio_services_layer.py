"""Unit tests for portfolio service layer (deposits, journal, dashboard, allocation)."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from data_ingestion.deposits_store import DepositsStore
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_allocation_service import (
    PortfolioAllocationService,
    classify_market_cap_bucket,
)
from services.portfolio_dashboard_service import PortfolioDashboardService
from services.portfolio_deposits_service import PortfolioDepositsService
from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService
from services.portfolio_zone_overview import zone_to_category


def _detail_row(**overrides: Any) -> PortfolioDetailRow:
    base = {
        "company": "Test Co",
        "ticker": "TST",
        "market_cap": 5_000_000_000,
        "pe_ratio": 15.0,
        "shares": 10.0,
        "current_price": 100.0,
        "current_value": 1000.0,
        "avg_cost_per_share": 90.0,
        "acquisition_value": 900.0,
        "profit": 100.0,
        "profit_pct": 11.1,
        "estimated_avg_price": 90.0,
        "medium_price_365d": 95.0,
        "price_180d": 98.0,
        "price_365d": 90.0,
        "change_180d_pct": 2.0,
        "change_365d_pct": 11.0,
        "weight_pct": 5.0,
        "dividend_yield_pct": 3.0,
        "dividend_per_share": 3.0,
        "annual_income": 30.0,
        "dividend_weight_pct": 5.0,
        "income_weight_pct": 5.0,
        "dividends_paid": 0.0,
        "growth_years": 10,
        "commission": 0.0,
        "sector": "Consumer",
        "acquisition_share_pct": 5.0,
        "analyst_rating": "BUY",
        "price_to_fcf": 10.0,
        "computed_dividend": "3.00 (3.00%)",
        "ex_dividend_date": None,
        "dividend_pay_date": None,
        "data_source": "test",
    }
    base.update(overrides)
    return PortfolioDetailRow(**base)


def test_deposits_service_summarize(sample_deposits: DepositsStore) -> None:
    service = PortfolioDepositsService(store=sample_deposits)
    summary = service.summarize()
    assert summary.total_deposits_eur == 1500.0
    assert summary.total_deposits_usd == 1650.0
    assert summary.latest_portfolio_eur == 10800.0
    assert summary.month_count == 2
    assert summary.gain_eur == 10800.0 - 1500.0


def test_dashboard_evolution_and_metrics(sample_deposits: DepositsStore) -> None:
    deposits = sample_deposits.list_deposits()
    dashboard = PortfolioDashboardService(
        deposits_service=PortfolioDepositsService(store=sample_deposits)
    )
    df = dashboard.evolution_dataframe(deposits)
    assert len(df) == 2
    assert df.iloc[0]["cumulative_deposits_eur"] == 1000.0
    assert df.iloc[1]["cumulative_deposits_eur"] == 1500.0
    assert df.iloc[1]["mom_change_pct"] == pytest.approx(8.0, rel=0.01)

    metrics = dashboard.build_metrics(deposits)
    assert metrics.avg_monthly_deposit_eur == 750.0
    assert metrics.months_since_start == 1
    assert metrics.deposits.month_count == 2


def test_dashboard_evolution_skips_zero_portfolio(tmp_path: Path) -> None:
    store = DepositsStore(db_path=tmp_path / "evo.db", seed=False)
    store.upsert_deposit(
        year=2026,
        month=4,
        label="April 2026",
        deposit_eur=0.0,
        deposit_usd=0.0,
        portfolio_eur=117565.63,
    )
    store.upsert_deposit(
        year=2026,
        month=5,
        label="May 2026",
        deposit_eur=4111.6,
        deposit_usd=4821.01,
        portfolio_eur=0.0,
    )
    dashboard = PortfolioDashboardService(deposits_service=PortfolioDepositsService(store=store))
    df = dashboard.evolution_dataframe()
    may = df.iloc[1]
    assert may["deposit_eur"] == 4111.6
    assert may["cumulative_deposits_eur"] == pytest.approx(4111.6)
    assert pd.isna(may["portfolio_eur"])
    assert pd.isna(may["gain_vs_deposits_eur"])
    assert pd.isna(may["mom_change_pct"])


def test_dashboard_empty_deposits_no_keyerror(tmp_path: Path) -> None:
    empty_store = DepositsStore(db_path=tmp_path / "empty.db", seed=False)
    dashboard = PortfolioDashboardService(
        deposits_service=PortfolioDepositsService(store=empty_store)
    )
    df = dashboard.evolution_dataframe()
    assert list(df.columns) == list(PortfolioDashboardService._empty_evolution_frame().columns)
    assert dashboard.create_gain_chart() is None
    metrics = dashboard.build_metrics()
    assert metrics.deposits.month_count == 0


def test_dashboard_holdings_from_rows() -> None:
    rows = [
        _detail_row(ticker="A", current_value=600.0, acquisition_value=500.0, annual_income=20.0),
        _detail_row(ticker="B", current_value=400.0, acquisition_value=500.0, annual_income=10.0),
    ]
    snap = PortfolioDashboardService.holdings_from_rows(rows)
    assert snap.positions == 2
    assert snap.current_value_usd == 1000.0
    assert snap.profit_usd == 0.0
    assert snap.annual_dividend_income_usd == 30.0


def test_purchase_journal_summarize_and_estimates(
    portfolio_with_trades: tuple[PortfolioStore, PurchaseJournalStore],
) -> None:
    portfolio, journal = portfolio_with_trades
    service = PortfolioPurchaseJournalService(
        journal_store=journal,
        portfolio_store=portfolio,
    )
    records = service.list_purchases()
    summary = service.summarize(records)
    assert summary.total_lots == 2
    assert summary.symbols_with_buys == 1
    assert summary.symbols_in_portfolio == 1

    lots = service.build_estimated_lots(records)
    assert len(lots) == 2
    total_value = sum(lot.estimated_value_usd for lot in lots)
    holding = portfolio.get_holding("KO")
    assert holding is not None
    assert total_value == pytest.approx(holding.acquisition_value, rel=0.01)

    splits = service.acquisition_split(records)
    assert len(splits) == 1
    assert splits[0].symbol == "KO"
    assert splits[0].lot_count == 2


def test_purchase_journal_symbols_without_journal(
    portfolio_store: PortfolioStore,
    journal_store: PurchaseJournalStore,
) -> None:
    portfolio_store.upsert_holding("A", shares=1, avg_cost_per_share=1.0)
    portfolio_store.upsert_holding("B", shares=1, avg_cost_per_share=1.0)
    journal_store.add_purchase("A", date(2024, 1, 1), 1.0)
    service = PortfolioPurchaseJournalService(
        journal_store=journal_store,
        portfolio_store=portfolio_store,
    )
    assert service.symbols_without_journal() == ["B"]


@pytest.mark.parametrize(
    "cap,expected",
    [
        (None, "Unknown"),
        (500_000_000, "<1B"),
        (5_000_000_000, "1–10B"),  # noqa: RUF001
        (50_000_000_000, "10–200B"),  # noqa: RUF001
        (500_000_000_000, ">200B"),
    ],
)
def test_market_cap_bucket(cap: float | None, expected: str) -> None:
    assert classify_market_cap_bucket(cap) == expected


def test_sector_allocation_weights() -> None:
    rows = [
        _detail_row(ticker="A", sector="Tech", current_value=600.0),
        _detail_row(ticker="B", sector="Tech", current_value=400.0),
        _detail_row(ticker="C", sector="Health", current_value=1000.0),
    ]
    df = PortfolioAllocationService().sector_allocation(rows)
    tech = df[df["Sector"] == "Tech"].iloc[0]
    assert tech["Weight %"] == pytest.approx(50.0, rel=0.01)
    assert tech["Positions"] == 2


@pytest.mark.parametrize(
    "zone,expected",
    [
        ("Deep Value", "green"),
        ("Value", "green"),
        ("Fair Value", "yellow"),
        ("Caution", "red"),
        ("Expensive", "red"),
        ("N/A", "unknown"),
    ],
)
def test_zone_to_category(zone: str, expected: str) -> None:
    assert zone_to_category(zone) == expected
