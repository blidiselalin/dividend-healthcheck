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
from services.portfolio_monthly_valuation import compute_monthly_portfolio_eur


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
    assert values["2025-03"] == pytest.approx(15 * 60.0 * 0.92, rel=0.01)


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
