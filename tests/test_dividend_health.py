"""Tests for simple dividend health labels."""

from __future__ import annotations

from models.stock import DividendHistory, StockData
from services.dividend_health import (
    HEALTH_HEALTHY,
    HEALTH_RISKY,
    HEALTH_UNKNOWN,
    HEALTH_WATCH,
    assess_dividend_health,
)


def _stock(**overrides) -> StockData:
    base = StockData(
        symbol="KO",
        name="Coca-Cola",
        sector="Consumer Staples",
        industry="Beverages",
        dividend_yield_pct=3.0,
        payout_ratio_pct=55.0,
        dividend_coverage=1.9,
        dividend_history=DividendHistory(
            consecutive_years=10,
            total_years=12,
            cagr_5y=5.0,
            cagr_10y=4.0,
            current_annual=1.8,
            payment_frequency=4,
        ),
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_healthy_when_metrics_normal() -> None:
    result = assess_dividend_health(_stock())
    assert result.label == HEALTH_HEALTHY


def test_risky_when_payout_high() -> None:
    result = assess_dividend_health(_stock(payout_ratio_pct=92.0))
    assert result.label == HEALTH_RISKY


def test_watch_when_growth_slow() -> None:
    result = assess_dividend_health(
        _stock(
            dividend_history=DividendHistory(
                consecutive_years=10,
                total_years=12,
                cagr_5y=1.0,
                cagr_10y=4.0,
                current_annual=1.8,
                payment_frequency=4,
            )
        )
    )
    assert result.label == HEALTH_WATCH


def test_not_enough_data_when_empty() -> None:
    result = assess_dividend_health(
        _stock(
            dividend_yield_pct=None,
            payout_ratio_pct=None,
            dividend_history=None,
        )
    )
    assert result.label == HEALTH_UNKNOWN
