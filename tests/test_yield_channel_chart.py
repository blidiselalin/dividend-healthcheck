"""Tests for yield channel validation and chart data prep."""

from __future__ import annotations

from datetime import datetime, timedelta

from services.yield_channel_chart import (
    YieldChannelData,
    validate_yield_channel_data,
    _ordered_percentiles,
)


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
