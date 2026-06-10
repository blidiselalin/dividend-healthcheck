"""Current-month paid dividend summaries."""

from __future__ import annotations

from datetime import date

from services.portfolio_dividend_calendar import (
    HoldingMonthDividend,
    MonthDividendExposure,
    month_start,
)
from services.portfolio_month_dividends import (
    CurrentMonthPaidDividends,
    gross_paid_in_calendar_month,
    month_label_for,
    net_paid_in_calendar_month,
    net_received_through,
)
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


def test_gross_paid_in_calendar_month_empty_db(tmp_path) -> None:
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


def test_net_paid_in_calendar_month_from_seed(tmp_path) -> None:
    from data_ingestion.dividend_income_store import DividendIncomeStore

    db = tmp_path / "portfolio.db"
    store = DividendIncomeStore(db, seed=True)
    assert net_paid_in_calendar_month(2026, 4, store=store) == 342.52
    assert net_paid_in_calendar_month(2026, 5, store=store) is None


def test_portfolio_section_labels_renamed() -> None:
    assert PORTFOLIO_SECTION_LABELS == [
        "Home",
        "Holdings",
        "Dividend income",
        "Dividend growth",
        "Purchase journal",
        "Deposits & benchmarks",
    ]


def test_net_received_through_applies_withholding() -> None:
    assert net_received_through(100.0, year=2025) == 90.0
    assert net_received_through(100.0, year=2026) == 84.0
    assert net_received_through(0.0, year=2026) is None


def test_current_month_paid_returns_zero_snapshot_for_rows() -> None:
    from services.portfolio_month_dividends import current_month_paid_dividends

    snapshot = current_month_paid_dividends(
        rows=[],
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
