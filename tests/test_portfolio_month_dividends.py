"""Current-month paid dividend summaries."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from data_ingestion.models import DividendRecord, StockDocument
from data_ingestion.portfolio_store import PortfolioHolding, PortfolioStore
from services.portfolio_dividend_calendar import (
    HoldingMonthDividend,
    MonthDividendExposure,
    month_start,
)
from services.portfolio_month_dividends import (
    CurrentMonthPaidDividends,
    current_month_paid_dividends,
    gross_paid_in_calendar_month,
    month_label_for,
    net_paid_in_calendar_month,
    net_received_through,
)
from services.portfolio_dividend_sync_service import sync_received_dividends
from ui.theme import PORTFOLIO_SECTION_LABELS, resolve_portfolio_section_label


def test_month_dividend_exposure_received_cash() -> None:
    month = month_start(date(2026, 5, 19))
    exposure = MonthDividendExposure(
        month_start=month,
        label="May 2026",
        total_cash=120.0,
        holdings=[
            HoldingMonthDividend(
                symbol="KO",
                company="Coca-Cola",
                shares=10,
                expected_cash=50.0,
                per_share=5.0,
                payment_date=date(2026, 5, 10),
                ex_date=date(2026, 4, 28),
                status="received",
            ),
            HoldingMonthDividend(
                symbol="O",
                company="Realty Income",
                shares=20,
                expected_cash=70.0,
                per_share=3.5,
                payment_date=date(2026, 5, 25),
                ex_date=date(2026, 5, 12),
                status="scheduled",
            ),
        ],
    )
    assert exposure.received_cash == 50.0
    assert exposure.received_payer_count == 1


def test_month_label_for_may_2026() -> None:
    assert month_label_for(date(2026, 5, 19)) == "May 2026"


def test_gross_paid_in_calendar_month_empty_db(tmp_path: Path) -> None:
    import sqlite3

    from data_ingestion.dividend_receipt_store import DividendReceiptStore

    db = tmp_path / "portfolio.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE holdings (symbol TEXT PRIMARY KEY)")

    gross, count = gross_paid_in_calendar_month(
        2026,
        5,
        through=date(2026, 5, 19),
        store=DividendReceiptStore(db),
    )
    assert gross == 0.0
    assert count == 0


def test_net_paid_in_calendar_month_from_seed(tmp_path: Path) -> None:
    from data_ingestion.dividend_income_store import DividendIncomeStore

    db = tmp_path / "portfolio.db"
    store = DividendIncomeStore(db, seed=True)
    assert net_paid_in_calendar_month(2026, 4, store=store) == 342.52
    assert net_paid_in_calendar_month(2026, 5, store=store) is None


def test_portfolio_section_labels_renamed() -> None:
    assert [
        "Home",
        "Holdings",
        "Dividend income",
        "Dividend growth",
        "Purchase journal",
        "Deposits & benchmarks",
    ] == PORTFOLIO_SECTION_LABELS


def test_net_received_through_applies_withholding() -> None:
    assert net_received_through(100.0, year=2025) == 90.0
    assert net_received_through(100.0, year=2026) == 84.0
    assert net_received_through(0.0, year=2026) is None


def test_compute_month_received_uses_journal_shares_and_pay_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_ingestion.models import DividendRecord, StockDocument
    from services.portfolio_month_dividends import compute_month_received_from_holdings
    from services.portfolio_purchase_journal_service import EstimatedPurchaseLot

    holding = PortfolioHolding(
        symbol="KO",
        shares=100.0,
        avg_cost_per_share=50.0,
        acquisition_value=5000.0,
        commission=0.0,
        dividends_paid=0.0,
        estimated_avg_price=50.0,
        sort_order=0,
    )
    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(
                ex_date=date(2026, 6, 10),
                payment_date=date(2026, 6, 15),
                amount=0.485,
            ),
            DividendRecord(
                ex_date=date(2026, 6, 12),
                payment_date=date(2026, 6, 15),
                amount=2.71,  # annual lump — must normalize
            ),
        ],
        payment_frequency=4,
        annual_dividend=2.71,
    )
    lots = [
        EstimatedPurchaseLot(
            symbol="KO",
            purchase_date=date(2024, 1, 1),
            label="01 Jan 2024",
            price_usd=50.0,
            estimated_shares=10.0,
            estimated_value_usd=500.0,
        ),
    ]
    monkeypatch.setattr(
        "services.portfolio_holding_detail_service.PortfolioHoldingDetailService.estimated_lots_for_symbol",
        lambda self, symbol: lots if symbol == "KO" else [],
    )

    gross, count = compute_month_received_from_holdings(
        [holding],
        {"KO": doc},
        reference_date=date(2026, 6, 19),
    )
    assert count == 2
    assert gross == pytest.approx(31.95, rel=0.01)


def test_current_month_paid_prefers_synced_receipts_over_live_compute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_ingestion.models import DividendRecord, StockDocument
    from data_ingestion.portfolio_store import PortfolioHolding
    from services.portfolio_month_dividends import current_month_paid_dividends

    holding = PortfolioHolding(
        symbol="KO",
        shares=10.0,
        avg_cost_per_share=50.0,
        acquisition_value=500.0,
        commission=0.0,
        dividends_paid=0.0,
        estimated_avg_price=50.0,
        sort_order=0,
    )
    doc = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(
                ex_date=date(2026, 6, 10),
                payment_date=date(2026, 6, 15),
                amount=0.485,
            ),
        ],
        payment_frequency=4,
        annual_dividend=1.94,
    )

    monkeypatch.setattr(
        "services.portfolio_month_dividends.PortfolioStore",
        lambda: type("Store", (), {"list_holdings": lambda self: [holding]})(),
    )
    monkeypatch.setattr(
        "services.portfolio_month_dividends.gross_paid_in_calendar_month",
        lambda *args, **kwargs: (489.22, 12),
    )
    monkeypatch.setattr(
        "services.portfolio_month_dividends.compute_month_received_from_holdings",
        lambda *args, **kwargs: (316.0, 8),
    )
    monkeypatch.setattr(
        "services.portfolio_month_dividends.net_paid_in_calendar_month",
        lambda *args, **kwargs: 410.94,
    )
    monkeypatch.setattr(
        "services.portfolio_month_dividends.gross_paid_in_synced_month",
        lambda *args, **kwargs: 489.22,
    )

    snapshot = current_month_paid_dividends(
        preload=type(
            "Preload",
            (),
            {"vector_docs": {"KO": doc}, "stock_data": {}, "yield_channels": {}},
        )(),
        reference_date=date(2026, 6, 19),
    )

    assert snapshot is not None
    assert snapshot.gross_usd == 489.22
    assert snapshot.payer_count == 12
    assert snapshot.net_usd == pytest.approx(410.94, rel=0.01)


def test_sync_stores_gross_and_net_monthly_totals(tmp_path: Path) -> None:
    def _doc_with_dividends() -> StockDocument:
        return StockDocument(
            symbol="KO",
            name="Coca-Cola",
            dividend_history=[
                DividendRecord(
                    ex_date=date(2024, 3, 14),
                    payment_date=date(2024, 4, 1),
                    amount=0.46,
                ),
            ],
        )

    db = tmp_path / "portfolio.db"
    portfolio = PortfolioStore(db_path=db, seed=False)
    from data_ingestion.purchase_journal_store import PurchaseJournalStore

    journal = PurchaseJournalStore(db_path=db, seed=False)
    portfolio.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)
    journal.add_purchase("KO", date(2024, 1, 1), 48.0)

    with patch(
        "services.portfolio_dividend_sync_service._load_documents",
        return_value={"KO": _doc_with_dividends()},
    ):
        sync_received_dividends(db_path=db)

    from data_ingestion.dividend_income_store import DividendIncomeStore

    store = DividendIncomeStore(db, seed=False)
    april = next(item for item in store.list_dividends() if item.year == 2024 and item.month == 4)
    assert april.gross_usd == pytest.approx(4.79, rel=0.01)
    assert april.net_usd == pytest.approx(4.31, rel=0.01)


def test_current_month_paid_returns_zero_snapshot_for_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from services.portfolio_month_dividends import current_month_paid_dividends

    monkeypatch.setattr(
        "services.portfolio_month_dividends.PortfolioStore",
        lambda: type(
            "Store",
            (),
            {"list_holdings": lambda self: []},
        )(),
    )
    monkeypatch.setattr(
        "services.portfolio_month_dividends.gross_paid_in_calendar_month",
        lambda *args, **kwargs: (0.0, 0),
    )
    monkeypatch.setattr(
        "services.portfolio_month_dividends.net_paid_in_calendar_month",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "services.portfolio_month_dividends.gross_paid_in_synced_month",
        lambda *args, **kwargs: None,
    )

    snapshot = current_month_paid_dividends(
        rows=[SimpleNamespace(ticker="KO", ex_dividend_date=None, dividend_pay_date=None)],
        reference_date=date(2026, 6, 10),
    )
    assert snapshot is not None
    assert snapshot.gross_usd == 0.0
    assert snapshot.net_usd is None
    assert snapshot.through_date == date(2026, 6, 10)
    assert snapshot.through_label == "through 10 Jun"


def test_current_month_paid_through_label() -> None:
    paid = CurrentMonthPaidDividends(
        month_label="June 2026",
        through_date=date(2026, 6, 19),
        gross_usd=50.0,
        net_usd=42.0,
        payer_count=2,
    )
    assert paid.through_label == "through 19 Jun"


def test_resolve_portfolio_section_label_legacy_overview_maps_home() -> None:
    assert resolve_portfolio_section_label(None) == "Home"
    assert resolve_portfolio_section_label("Overview") == "Home"
    assert resolve_portfolio_section_label("Income") == "Dividend income"
    assert resolve_portfolio_section_label("Home") == "Home"
