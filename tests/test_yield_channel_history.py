"""Tests for adaptive yield-channel history planning."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from data_ingestion.models import DividendRecord, PriceHistory, StockDocument
from utils.yield_channel_history import (
    estimate_history_years,
    plan_yield_channel_attempts,
    years_covered_by_frame,
    yield_channel_history_label,
)


def _doc_with_years(years: int) -> StockDocument:
    doc = StockDocument(symbol="INTU", name="Intuit")
    start = date.today() - timedelta(days=years * 365)
    doc.price_history = [
        PriceHistory(
            date=start + timedelta(days=i * 7),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0 + i * 0.01,
            volume=1,
        )
        for i in range(years * 52)
    ]
    doc.dividend_history = [
        DividendRecord(
            ex_date=date(start.year + y, 2, 15),
            payment_date=None,
            amount=1.0,
        )
        for y in range(years)
    ]
    return doc


def test_estimate_history_years_none_without_document() -> None:
    assert estimate_history_years(None) is None


def test_plan_attempts_defaults_when_no_library() -> None:
    attempts = plan_yield_channel_attempts(None, requested_years=10)
    assert (10, 120, 60) in attempts


def test_years_covered_by_frame_empty() -> None:
    assert years_covered_by_frame(pd.DataFrame()) == 0


def test_yield_channel_history_label_short_term() -> None:
    assert yield_channel_history_label(1, requested=10) == "short-term"


def test_estimate_history_years_from_library() -> None:
    doc = _doc_with_years(5)
    assert estimate_history_years(doc) == 5


def test_plan_attempts_shortens_window_for_newer_payers() -> None:
    doc = _doc_with_years(3)
    attempts = plan_yield_channel_attempts(doc, requested_years=10)
    years = [item[0] for item in attempts]
    assert 10 not in years
    assert 3 in years
    assert (3, 52, 26) in attempts


def test_years_covered_by_frame() -> None:
    index = pd.date_range("2020-01-01", periods=520, freq="W")
    frame = pd.DataFrame({"Close": [100.0] * 520}, index=index)
    assert years_covered_by_frame(frame) == 10


def test_yield_channel_history_label() -> None:
    assert "10-year" in yield_channel_history_label(10)
    assert "available history" in yield_channel_history_label(4, requested=10)
