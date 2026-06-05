"""Tests for yield channel validation and chart data prep."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pandas as pd

from data_ingestion.models import DividendRecord
from services.yield_channel_chart import (
    YieldChannelData,
    YieldChannelService,
    validate_yield_channel_data,
    _ordered_percentiles,
)
from utils.yfinance_history import align_dividends_to_price_index


def _sample_channel(n: int = 120) -> YieldChannelData:
    start = datetime(2018, 1, 1)
    dates = [start + timedelta(days=7 * i) for i in range(n)]
    prices = [50 + i * 0.05 for i in range(n)]
    yields = [2.8 + (i % 20) * 0.02 for i in range(n)]
    return YieldChannelData(
        symbol="KO",
        company_name="Coca-Cola",
        current_yield=3.1,
        current_price=prices[-1],
        current_dividend=1.84,
        avg_yield=3.0,
        median_yield=3.0,
        min_yield=2.5,
        max_yield=3.8,
        std_yield=0.3,
        yield_10th=2.7,
        yield_25th=2.85,
        yield_75th=3.15,
        yield_90th=3.4,
        deep_value_price=54.0,
        value_price=58.0,
        fair_value_price=61.0,
        caution_price=65.0,
        expensive_price=68.0,
        zone="Fair Value",
        zone_score=50.0,
        percentile=52.0,
        dates=dates,
        prices=prices,
        yields=yields,
        annual_dividends=yields,
        years_analyzed=10,
        data_points=n,
    )


def test_ordered_percentiles_monotonic():
    stats = _ordered_percentiles(
        {
            "p10": 3.5,
            "p25": 2.0,
            "median": 4.0,
            "p75": 3.0,
            "p90": 2.5,
            "mean": 3.0,
            "std": 0.5,
            "min": 2.0,
            "max": 4.0,
        }
    )
    assert stats["p10"] <= stats["p25"] <= stats["median"] <= stats["p75"] <= stats["p90"]


def test_validate_rejects_short_series():
    data = _sample_channel(n=10)
    assert validate_yield_channel_data(data) is None


def test_validate_accepts_clean_series():
    data = _sample_channel()
    clean = validate_yield_channel_data(data)
    assert clean is not None
    assert len(clean.dates) == len(clean.prices) == len(clean.yields)
    assert clean.deep_value_price <= clean.value_price <= clean.expensive_price


def test_align_dividends_maps_ex_date_to_next_trading_day():
    index = pd.date_range("2020-01-02", periods=5, freq="B")
    hist = pd.DataFrame({"Close": [100.0] * 5, "Dividends": [0.0] * 5}, index=index)
    # Ex-date on Saturday should land on Monday 2020-01-06
    divs = pd.Series({pd.Timestamp("2020-01-04"): 1.5})
    merged = align_dividends_to_price_index(hist, divs)
    assert merged["Dividends"].sum() == 1.5
    assert merged.loc[pd.Timestamp("2020-01-06"), "Dividends"] == 1.5


@patch("utils.yfinance_history.fetch_dividend_series", return_value=pd.Series(dtype=float))
def test_ensure_dividends_prefers_library_without_yfinance(mock_yf_divs):
    # ~2 years of business days so 2019 and 2020 ex-dates all map to trading rows
    index = pd.date_range("2019-01-02", periods=520, freq="B")
    hist = pd.DataFrame({"Close": [150.0] * 520, "Dividends": [0.0] * 520}, index=index)
    records = [
        DividendRecord(ex_date=date(2019, 2, 14), payment_date=None, amount=1.07),
        DividendRecord(ex_date=date(2019, 5, 15), payment_date=None, amount=1.07),
        DividendRecord(ex_date=date(2019, 8, 15), payment_date=None, amount=1.07),
        DividendRecord(ex_date=date(2019, 11, 15), payment_date=None, amount=1.07),
        DividendRecord(ex_date=date(2020, 2, 14), payment_date=None, amount=1.18),
        DividendRecord(ex_date=date(2020, 5, 15), payment_date=None, amount=1.18),
        DividendRecord(ex_date=date(2020, 8, 15), payment_date=None, amount=1.18),
        DividendRecord(ex_date=date(2020, 11, 15), payment_date=None, amount=1.18),
    ]
    service = YieldChannelService(vector_store=None)
    merged = service._ensure_dividends_on_history(hist, "ABBV", records)
    assert merged["Dividends"].sum() > 0
    assert service._dividend_payment_count(merged) >= 8
    mock_yf_divs.assert_not_called()


def test_align_dividends_handles_timezone_aware_ex_dates():
    index = pd.date_range("2020-01-02", periods=5, freq="B", tz="UTC")
    hist = pd.DataFrame({"Close": [100.0] * 5, "Dividends": [0.0] * 5}, index=index)
    divs = pd.Series(
        {pd.Timestamp("2020-01-04", tz="UTC"): 1.5},
    )
    merged = align_dividends_to_price_index(hist, divs)
    assert merged["Dividends"].sum() == 1.5
