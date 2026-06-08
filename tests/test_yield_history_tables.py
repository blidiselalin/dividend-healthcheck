"""Tests for yearly yield / dividend history tables."""

from __future__ import annotations

from datetime import date

from data_ingestion.models import DataSource, DividendRecord, StockDocument
from utils.yield_history_tables import (
    estimate_annual_dividend_for_year,
    year_column_label,
    yearly_dividend_per_share_table,
    yearly_yield_exposure_table,
)


def test_yearly_dividend_per_share_from_library():
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


def test_current_year_dividend_is_projected_for_comparison():
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


def test_estimate_annual_dividend_scales_partial_payments():
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


def test_yearly_yield_exposure_from_channel():
    class Channel:
        dates = [date(2023, 6, 1), date(2023, 12, 31), date(2024, 6, 1)]
        yields = [3.0, 3.2, 3.1]
        prices = [50.0, 52.0, 54.0]
        annual_dividends = [1.5, 1.6, 1.7]

    table = yearly_yield_exposure_table(Channel(), today=date(2024, 6, 1))
    assert "2023" in list(table["Year"])
    assert "2024 (est.)" in list(table["Year"])
    assert table.loc[table["Year"] == "2023", "Trailing div $"].iloc[0] == 1.6
