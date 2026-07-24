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
    MonthPortfolioValuation,
    _close_for_month_end,
    _mark_price_for_date,
    compute_monthly_portfolio_eur,
    compute_monthly_portfolio_valuations,
    continuous_monthly_deposits,
    fx_rates_carry_forward,
    pick_portfolio_eur_for_month,
    portfolio_eur_to_store,
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


def test_continuous_monthly_deposits_includes_current_month() -> None:
    from data_ingestion.deposits_store import MonthlyDeposit

    rows = [
        MonthlyDeposit(
            period=date(2025, 1, 1),
            label="January 2025",
            deposit_eur=1000.0,
            deposit_usd=1100.0,
            portfolio_eur=0.0,
            sort_order=1,
        ),
    ]
    expanded = continuous_monthly_deposits(
        rows,
        include_current_month=True,
        reference=date(2026, 7, 15),
    )
    assert expanded[-1].period_key == "2026-07"
    assert len(expanded) >= 19


def test_mark_price_for_current_month_uses_snapshot_when_history_stale() -> None:
    series = [(date(2026, 7, 18), 50.0)]
    today = date(2026, 7, 23)
    assert _mark_price_for_date(
        series,
        today,
        snapshot_price=55.0,
        reference=today,
    ) == pytest.approx(55.0)


def test_mark_price_for_past_month_uses_last_in_month_close() -> None:
    series = [
        (date(2025, 1, 31), 50.0),
        (date(2025, 2, 28), 52.0),
    ]
    assert _mark_price_for_date(
        series,
        date(2025, 1, 31),
        snapshot_price=99.0,
        reference=date(2026, 7, 23),
    ) == pytest.approx(50.0)


def test_continuous_monthly_deposits_fills_gaps() -> None:
    from data_ingestion.deposits_store import MonthlyDeposit

    rows = [
        MonthlyDeposit(
            period=date(2025, 1, 1),
            label="January 2025",
            deposit_eur=1000.0,
            deposit_usd=1100.0,
            portfolio_eur=0.0,
            sort_order=1,
        ),
        MonthlyDeposit(
            period=date(2025, 3, 1),
            label="March 2025",
            deposit_eur=500.0,
            deposit_usd=550.0,
            portfolio_eur=0.0,
            sort_order=2,
        ),
    ]
    expanded = continuous_monthly_deposits(rows, include_current_month=False)
    assert len(expanded) == 3
    assert expanded[1].period.month == 2
    assert expanded[1].deposit_eur == 0.0


def test_evolution_includes_zero_deposit_months_with_portfolio(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    journal = PurchaseJournalStore(db_path=db, seed=False)
    deposits = DepositsStore(db_path=db, seed=False)

    journal.add_purchase("KO", date(2025, 1, 10), 50.0, shares=10.0, side="buy")
    portfolio.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)
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
        month=3,
        label="March 2025",
        deposit_eur=500.0,
        deposit_usd=550.0,
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

    fx_market = [
        (date(2025, 1, 31), 1000 / 1100),
        (date(2025, 2, 28), 500 / 550),
        (date(2025, 3, 31), 500 / 550),
    ]

    dashboard = PortfolioDashboardService(deposits_service=PortfolioDepositsService(store=deposits))
    with (
        patch(
            "services.shared_market_db.load_documents",
            return_value={"KO": ko_prices},
        ),
        patch(
            "services.fx_rate_service.load_eur_usd_market_series",
            return_value=fx_market,
        ),
    ):
        df = dashboard.evolution_dataframe(db_path=db, include_current_month=False)

    assert len(df) == 3
    feb = df.iloc[1]
    assert feb["deposit_eur"] == 0.0
    assert feb["portfolio_eur"] == pytest.approx(10 * 52.0 * (1000 / 1100), rel=0.02)


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

    fx_market = [
        (date(2025, 1, 31), 1000 / 1100),
        (date(2025, 2, 28), 500 / 550),
        (date(2025, 3, 31), 500 / 550),
    ]

    with (
        patch(
            "services.shared_market_db.load_documents",
            return_value={"KO": ko_prices},
        ),
        patch(
            "services.fx_rate_service.load_eur_usd_market_series",
            return_value=fx_market,
        ),
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


def test_mark_price_for_current_month_uses_max_of_history_snapshot_live() -> None:
    series = [(date(2026, 7, 22), 50.0)]
    today = date(2026, 7, 23)
    assert _mark_price_for_date(
        series,
        today,
        snapshot_price=55.0,
        live_price=58.0,
        reference=today,
    ) == pytest.approx(58.0)


def test_portfolio_eur_to_store_requires_full_coverage() -> None:
    partial = MonthPortfolioValuation(
        portfolio_usd=1000.0,
        portfolio_eur=900.0,
        symbols_held=3,
        symbols_priced=2,
    )
    assert portfolio_eur_to_store(stored=1200.0, valuation=partial) == 1200.0
    assert portfolio_eur_to_store(stored=None, valuation=partial) is None
    full = MonthPortfolioValuation(
        portfolio_usd=1000.0,
        portfolio_eur=900.0,
        symbols_held=2,
        symbols_priced=2,
    )
    assert portfolio_eur_to_store(stored=1200.0, valuation=full) == 900.0


def test_current_month_uses_open_holding_shares(tmp_path: Path) -> None:
    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    journal = PurchaseJournalStore(db_path=db, seed=False)
    deposits = DepositsStore(db_path=db, seed=False)

    journal.add_purchase("KO", date(2026, 1, 10), 50.0, shares=10.0, side="buy")
    portfolio.upsert_holding("KO", shares=15, avg_cost_per_share=50.0)
    portfolio.upsert_holding("PEP", shares=5, avg_cost_per_share=80.0)
    deposits.upsert_deposit(
        year=2026,
        month=7,
        label="July 2026",
        deposit_eur=0.0,
        deposit_usd=0.0,
        portfolio_eur=0.0,
    )

    docs = {
        "KO": _price_doc("KO", [(date(2026, 7, 22), 60.0)]),
        "PEP": _price_doc("PEP", [(date(2026, 7, 22), 100.0)]),
    }
    timeline = continuous_monthly_deposits(
        deposits.list_deposits(),
        include_current_month=True,
        reference=date(2026, 7, 23),
    )
    with (
        patch("services.shared_market_db.load_documents", return_value=docs),
        patch(
            "services.portfolio_monthly_valuation._load_live_prices",
            return_value={"KO": 62.0, "PEP": 101.0},
        ),
    ):
        values = compute_monthly_portfolio_valuations(timeline, db_path=db)

    july = values["2026-07"]
    assert july.symbols_held == 2
    assert july.symbols_priced == 2
    assert july.portfolio_usd == pytest.approx(15 * 62.0 + 5 * 101.0)


def test_pick_portfolio_prefers_stored_when_price_coverage_incomplete() -> None:
    partial = MonthPortfolioValuation(
        portfolio_usd=1000.0,
        portfolio_eur=900.0,
        symbols_held=3,
        symbols_priced=2,
    )
    assert pick_portfolio_eur_for_month(stored=1200.0, valuation=partial) == 1200.0
    assert pick_portfolio_eur_for_month(stored=None, valuation=partial) == 900.0
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
    df = dashboard.evolution_dataframe(use_computed_portfolio=False, include_current_month=False)

    assert df.iloc[0]["cumulative_deposits_eur"] == 1000.0
    assert df.iloc[1]["cumulative_deposits_eur"] == 1500.0
    assert pd.isna(df.iloc[0]["portfolio_eur"])

    chart = dashboard.create_evolution_chart(
        use_computed_portfolio=False,
        include_current_month=False,
    )
    assert chart is not None
    cumulative = chart.data[0].y
    assert list(cumulative) == [1000.0, 1500.0]
