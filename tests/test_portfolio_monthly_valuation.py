"""Tests for month-end portfolio valuation and dashboard evolution."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from data_ingestion.deposits_store import DepositsStore
from data_ingestion.models import PriceHistory, StockDocument
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore
from services.portfolio_dashboard_service import PortfolioDashboardService
from services.portfolio_deposits_service import PortfolioDepositsService
from services.portfolio_monthly_valuation import (
    _close_for_month_end,
    compute_monthly_portfolio_eur,
    fx_rates_carry_forward,
    pick_portfolio_eur_for_month,
    shares_from_records,
    valuation_as_of,
)


def _price_doc(symbol: str, points: list[tuple[date, float]]) -> StockDocument:
    return StockDocument(
        symbol=symbol,
        name=symbol,
        price_history=[
            PriceHistory(
                date=point_date,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000,
                adjusted_close=close,
            )
            for point_date, close in points
        ],
    )


def test_compute_monthly_portfolio_eur_from_journal_and_prices(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    journal = PurchaseJournalStore(db_path=db, seed=False)
    deposits = DepositsStore(db_path=db, seed=False)

    journal.add_purchase("KO", date(2025, 1, 10), 50.0, shares=10.0, side="buy")
    journal.add_purchase("KO", date(2025, 3, 5), 55.0, shares=5.0, side="buy")
    portfolio.upsert_holding("KO", shares=15, avg_cost_per_share=51.67)

    deposits.upsert_deposit(
        year=2025,
        month=1,
        label="January 2025",
        deposit_eur=1000.0,
        deposit_usd=1100.0,
        portfolio_eur=0.0,
    )
    deposits.upsert_deposit(
        year=2025,
        month=2,
        label="February 2025",
        deposit_eur=500.0,
        deposit_usd=550.0,
        portfolio_eur=0.0,
    )
    deposits.upsert_deposit(
        year=2025,
        month=3,
        label="March 2025",
        deposit_eur=0.0,
        deposit_usd=0.0,
        portfolio_eur=0.0,
    )

    ko_prices = _price_doc(
        "KO",
        [
            (date(2025, 1, 31), 50.0),
            (date(2025, 2, 28), 52.0),
            (date(2025, 3, 31), 60.0),
        ],
    )

    with patch(
        "services.shared_market_db.load_documents",
        return_value={"KO": ko_prices},
    ):
        values = compute_monthly_portfolio_eur(deposits.list_deposits(), db_path=db)

    assert values["2025-01"] == pytest.approx(10 * 50.0 * (1000 / 1100), rel=0.01)
    assert values["2025-02"] == pytest.approx(10 * 52.0 * (500 / 550), rel=0.01)
    assert values["2025-03"] == pytest.approx(15 * 60.0 * (500 / 550), rel=0.01)


def test_shares_from_records_accounts_for_sells(
    journal_store: PurchaseJournalStore,
) -> None:
    journal_store.add_purchase(
        "AAPL",
        date(2025, 1, 10),
        150.0,
        shares=10.0,
        side="buy",
        source="ibkr",
    )
    journal_store.add_purchase(
        "AAPL",
        date(2025, 6, 1),
        170.0,
        shares=4.0,
        side="sell",
        source="ibkr",
    )
    records = journal_store.list_purchases(portfolio_only=False)
    assert shares_from_records(records, date(2025, 3, 31)) == pytest.approx(10.0)
    assert shares_from_records(records, date(2025, 7, 31)) == pytest.approx(6.0)


def test_pick_portfolio_prefers_stored_when_price_coverage_incomplete() -> None:
    from services.portfolio_monthly_valuation import MonthPortfolioValuation

    partial = MonthPortfolioValuation(
        portfolio_usd=1000.0,
        portfolio_eur=900.0,
        symbols_held=3,
        symbols_priced=2,
    )
    assert pick_portfolio_eur_for_month(stored=1200.0, valuation=partial) == 1200.0
    assert pick_portfolio_eur_for_month(stored=None, valuation=partial) is None
    full = MonthPortfolioValuation(
        portfolio_usd=1000.0,
        portfolio_eur=900.0,
        symbols_held=2,
        symbols_priced=2,
    )
    assert pick_portfolio_eur_for_month(stored=1200.0, valuation=full) == 900.0


def test_close_for_month_end_prefers_in_month_then_falls_back() -> None:
    series = [
        (date(2025, 1, 31), 50.0),
        (date(2025, 2, 28), 52.0),
        (date(2025, 3, 31), 60.0),
    ]
    assert _close_for_month_end(series, date(2025, 2, 28)) == pytest.approx(52.0)
    assert _close_for_month_end(series, date(2025, 2, 15)) == pytest.approx(50.0)
    assert _close_for_month_end(series, date(2025, 4, 30)) == pytest.approx(60.0)


def test_valuation_as_of_caps_current_month_at_today() -> None:
    today = date(2026, 7, 23)
    assert valuation_as_of(date(2026, 7, 1), reference=today) == today
    assert valuation_as_of(date(2025, 12, 1), reference=today) == date(2025, 12, 31)


def test_fx_rates_carry_forward_from_prior_deposit_month() -> None:
    from data_ingestion.deposits_store import MonthlyDeposit

    rows = [
        MonthlyDeposit(
            period=date(2025, 1, 1),
            label="Jan",
            deposit_eur=1000.0,
            deposit_usd=1100.0,
            portfolio_eur=0.0,
            sort_order=1,
        ),
        MonthlyDeposit(
            period=date(2025, 2, 1),
            label="Feb",
            deposit_eur=0.0,
            deposit_usd=0.0,
            portfolio_eur=0.0,
            sort_order=2,
        ),
    ]
    rates = fx_rates_carry_forward(rows)
    assert rates["2025-02"] == pytest.approx(1000 / 1100)


def test_evolution_chart_uses_full_cumulative_deposit_timeline(tmp_path: Path) -> None:
    store = DepositsStore(db_path=tmp_path / "evo.db", seed=False)
    store.upsert_deposit(
        year=2026,
        month=1,
        label="Jan 2026",
        deposit_eur=1000.0,
        deposit_usd=0.0,
        portfolio_eur=0.0,
    )
    store.upsert_deposit(
        year=2026,
        month=2,
        label="Feb 2026",
        deposit_eur=500.0,
        deposit_usd=0.0,
        portfolio_eur=10800.0,
    )
    dashboard = PortfolioDashboardService(deposits_service=PortfolioDepositsService(store=store))
    df = dashboard.evolution_dataframe(use_computed_portfolio=False)

    assert df.iloc[0]["cumulative_deposits_eur"] == 1000.0
    assert df.iloc[1]["cumulative_deposits_eur"] == 1500.0
    assert pd.isna(df.iloc[0]["portfolio_eur"])

    chart = dashboard.create_evolution_chart(use_computed_portfolio=False)
    assert chart is not None
    cumulative = chart.data[0].y
    assert list(cumulative) == [1000.0, 1500.0]
