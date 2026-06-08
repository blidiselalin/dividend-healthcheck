"""Tests for yearly yield / dividend history tables."""

from __future__ import annotations

from datetime import date

from data_ingestion.models import DataSource, DividendRecord, StockDocument
from utils.yield_history_tables import (
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
    assert list(table["Year"]) == [2023, 2024]
    assert table.loc[table["Year"] == 2023, "Dividend / share $"].iloc[0] == 0.92


def test_yearly_yield_exposure_from_channel():
    class Channel:
        dates = [date(2023, 6, 1), date(2023, 12, 31), date(2024, 6, 1)]
        yields = [3.0, 3.2, 3.1]
        prices = [50.0, 52.0, 54.0]
        annual_dividends = [1.5, 1.6, 1.7]

    table = yearly_yield_exposure_table(Channel())
    assert 2023 in list(table["Year"])
    assert 2024 in list(table["Year"])
    assert table.loc[table["Year"] == 2024, "Trailing div $"].iloc[0] == 1.7
