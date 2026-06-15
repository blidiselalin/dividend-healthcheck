"""Tests for yearly yield / dividend history tables."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date

from data_ingestion.models import DataSource, DividendRecord, StockDocument
from utils.yield_history_tables import (
    estimate_annual_dividend_for_year,
    year_column_label,
    yearly_dividend_per_share_table,
    yearly_yield_exposure_table,
)


def test_estimate_annual_dividend_uses_declared_rate() -> None:
    doc = type("Doc", (), {"annual_dividend": 6.56, "dividend_rate": None})()
    display, status, ytd = estimate_annual_dividend_for_year(
        2026,
        1.64,
        1,
        document=doc,
        today=date(2026, 5, 19),
    )
    assert display == 6.56
    assert "declared" in status.lower()
    assert ytd == 1.64


def test_estimate_annual_dividend_uses_prior_year() -> None:
    records = [
        DividendRecord(ex_date=date(2024, 2, 1), payment_date=None, amount=4.0),
        DividendRecord(ex_date=date(2025, 2, 1), payment_date=None, amount=0.5),
    ]
    display, status, _ = estimate_annual_dividend_for_year(
        2025,
        0.5,
        1,
        all_records=records,
        today=date(2025, 3, 1),
    )
    assert display == 4.0
    assert "prior year" in status.lower()


def test_estimate_annual_dividend_scales_ytd_by_month() -> None:
    display, status, _ = estimate_annual_dividend_for_year(
        2025,
        1.0,
        1,
        today=date(2025, 3, 1),
    )
    assert display == 4.0
    assert "YTD scaled" in status


def test_complete_year_returns_summed_total() -> None:
    display, status, ytd = estimate_annual_dividend_for_year(
        2023,
        1.84,
        4,
        today=date(2026, 5, 19),
    )
    assert display == 1.84
    assert status == "Complete"
    assert ytd is None


def test_current_year_with_full_annual_schedule_is_complete() -> None:
    doc = type("Doc", (), {"annual_dividend": 1.2, "dividend_rate": None, "payment_frequency": 1})()
    display, status, ytd = estimate_annual_dividend_for_year(
        2026,
        1.2,
        1,
        document=doc,
        all_records=[DividendRecord(ex_date=date(2026, 3, 1), payment_date=None, amount=1.2)],
        today=date(2026, 6, 1),
    )
    assert display == 1.2
    assert status == "Complete"
    assert ytd is None


def test_yearly_dividend_per_share_from_library() -> None:
    doc = StockDocument(symbol="KO", name="Coca-Cola", source=DataSource.YAHOO)
    doc.dividend_history = [
        DividendRecord(ex_date=date(2023, 2, 1), payment_date=None, amount=0.46),
        DividendRecord(ex_date=date(2023, 8, 1), payment_date=None, amount=0.46),
        DividendRecord(ex_date=date(2024, 2, 1), payment_date=None, amount=0.48),
        DividendRecord(ex_date=date(2024, 8, 1), payment_date=None, amount=0.48),
    ]
    table = yearly_dividend_per_share_table(doc)
    assert list(table.columns) == ["Year", "Dividend / share $"]
    assert list(table["Year"]) == ["2023", "2024"]
    assert table.loc[table["Year"] == "2023", "Dividend / share $"].iloc[0] == 0.92


def test_current_year_dividend_is_projected_for_comparison() -> None:
    doc = StockDocument(symbol="ABBV", name="AbbVie", source=DataSource.YAHOO)
    doc.annual_dividend = 6.56
    doc.dividend_history = [
        DividendRecord(ex_date=date(2025, 2, 1), payment_date=None, amount=1.64),
        DividendRecord(ex_date=date(2025, 5, 1), payment_date=None, amount=1.64),
        DividendRecord(ex_date=date(2025, 8, 1), payment_date=None, amount=1.64),
        DividendRecord(ex_date=date(2025, 11, 1), payment_date=None, amount=1.64),
        DividendRecord(ex_date=date(2026, 2, 1), payment_date=None, amount=1.64),
    ]
    table = yearly_dividend_per_share_table(doc)
    current = table.loc[table["Year"] == year_column_label(2026, today=date(2026, 5, 19))]
    assert not current.empty
    assert current["Dividend / share $"].iloc[0] == 6.56


def test_current_year_dividend_table_omits_estimate_for_completed_annual_payer() -> None:
    doc = StockDocument(symbol="MAIN", name="Main Street Capital", source=DataSource.YAHOO)
    doc.payment_frequency = 1
    doc.annual_dividend = 1.2
    doc.dividend_history = [
        DividendRecord(ex_date=date(2025, 3, 1), payment_date=None, amount=1.1),
        DividendRecord(ex_date=date(2026, 3, 1), payment_date=None, amount=1.2),
    ]

    from utils import yield_history_tables

    original_date = yield_history_tables.date
    yield_history_tables.date = type("date", (), {"today": staticmethod(lambda: date(2026, 6, 1))})
    try:
        table = yearly_dividend_per_share_table(doc)
    finally:
        yield_history_tables.date = original_date

    assert "2026" in list(table["Year"])
    assert "2026 (est.)" not in list(table["Year"])
    assert table.loc[table["Year"] == "2026", "Dividend / share $"].iloc[0] == 1.2


def test_estimate_annual_dividend_scales_partial_payments() -> None:
    records = [
        DividendRecord(ex_date=date(2024, 2, 1), payment_date=None, amount=1.0),
        DividendRecord(ex_date=date(2024, 5, 1), payment_date=None, amount=1.0),
        DividendRecord(ex_date=date(2024, 8, 1), payment_date=None, amount=1.0),
        DividendRecord(ex_date=date(2024, 11, 1), payment_date=None, amount=1.0),
        DividendRecord(ex_date=date(2025, 2, 1), payment_date=None, amount=1.1),
    ]
    display, status, ytd = estimate_annual_dividend_for_year(
        2025,
        1.1,
        1,
        all_records=records,
        today=date(2025, 3, 1),
    )
    assert display == 4.4
    assert "Estimated" in status
    assert ytd == 1.1


def test_yearly_yield_exposure_from_channel() -> None:
    from typing import ClassVar

    class Channel:
        dates: ClassVar[list[date]] = [date(2023, 6, 1), date(2023, 12, 31), date(2024, 6, 1)]
        yields: ClassVar[list[float]] = [3.0, 3.2, 3.1]
        prices: ClassVar[list[float]] = [50.0, 52.0, 54.0]
        annual_dividends: ClassVar[list[float]] = [1.5, 1.6, 1.7]

    table = yearly_yield_exposure_table(Channel(), today=date(2024, 6, 1))
    assert "2023" in list(table["Year"])
    assert "2024 (est.)" in list(table["Year"])
    assert table.loc[table["Year"] == "2023", "Trailing div $"].iloc[0] == 1.6
