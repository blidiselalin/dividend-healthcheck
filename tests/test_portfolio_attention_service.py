"""Tests for portfolio attention watchlist."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from typing import Any

from services.portfolio_analysis_preload import PortfolioAnalysisPreload
from services.portfolio_attention_service import PortfolioAttentionService
from services.portfolio_details_service import PortfolioDetailRow
from services.yield_channel_chart import YieldChannelData


def _row(**overrides: Any) -> PortfolioDetailRow:
    base = {
        "company": "Test Co",
        "ticker": "TEST",
        "market_cap": 1e9,
        "pe_ratio": 15.0,
        "shares": 10.0,
        "current_price": 100.0,
        "current_value": 1000.0,
        "avg_cost_per_share": 90.0,
        "acquisition_value": 900.0,
        "profit": 100.0,
        "profit_pct": 11.1,
        "estimated_avg_price": 90.0,
        "medium_price_365d": 95.0,
        "price_180d": 98.0,
        "price_365d": 90.0,
        "change_180d_pct": 2.0,
        "change_365d_pct": 11.0,
        "weight_pct": 5.0,
        "dividend_yield_pct": 3.0,
        "dividend_per_share": 3.0,
        "annual_income": 30.0,
        "dividend_weight_pct": 5.0,
        "income_weight_pct": 5.0,
        "dividends_paid": 0.0,
        "growth_years": 10,
        "commission": 0.0,
        "sector": "Tech",
        "acquisition_share_pct": 5.0,
        "analyst_rating": "BUY",
        "price_to_fcf": 10.0,
        "computed_dividend": "3.00 (3.00%)",
        "ex_dividend_date": None,
        "dividend_pay_date": None,
        "data_source": "test",
    }
    base.update(overrides)
    return PortfolioDetailRow(**base)  # type: ignore[arg-type]


def _yield_channel(zone: str = "Expensive") -> YieldChannelData:
    return YieldChannelData(
        symbol="TEST",
        company_name="Test Co",
        current_yield=2.0,
        current_price=100.0,
        current_dividend=2.0,
        avg_yield=3.0,
        median_yield=3.0,
        min_yield=2.0,
        max_yield=5.0,
        std_yield=0.5,
        yield_10th=2.5,
        yield_25th=2.8,
        yield_75th=3.5,
        yield_90th=4.0,
        deep_value_price=120.0,
        value_price=110.0,
        fair_value_price=105.0,
        caution_price=95.0,
        expensive_price=85.0,
        zone=zone,
        zone_score=20.0,
        percentile=10.0,
        dates=[],
        prices=[],
        yields=[],
        annual_dividends=[],
        years_analyzed=10,
        data_points=120,
    )


def test_flags_expensive_zone_and_loss() -> None:
    service = PortfolioAttentionService()
    row = _row(ticker="ARE", profit_pct=-22.0, analyst_rating="AVOID")
    preload = PortfolioAnalysisPreload(
        stock_data={},
        yield_channels={"ARE": _yield_channel("Expensive")},
        vector_docs={},
    )
    summary = service.build_summary([row], preload, reference_date=date(2026, 5, 13))
    assert summary.total >= 1
    assert summary.dividend_total == 0
    item = summary.risk_items[0]
    assert "Exposure" in item.categories
    assert "Estimates" in item.categories
    assert item.severity in ("high", "medium")


def test_flags_upcoming_ex_dividend() -> None:
    service = PortfolioAttentionService()
    ex = date(2026, 5, 18)
    row = _row(ticker="KO", ex_dividend_date=ex)
    preload = PortfolioAnalysisPreload(stock_data={}, yield_channels={}, vector_docs={})
    summary = service.build_summary([row], preload, reference_date=date(2026, 5, 13))
    assert summary.dividend_total >= 1
    assert summary.total == 0
    assert all(item.categories == ("Dividend",) for item in summary.dividend_items)
    item = summary.dividend_items[0]
    assert item.timing == "Upcoming ex-date"
    assert "Severity" not in service.to_dataframe(summary, list_kind="dividend").columns
    assert "Timing" in service.to_dataframe(summary, list_kind="dividend").columns


def test_paid_dividend_not_listed() -> None:
    service = PortfolioAttentionService()
    row = _row(
        ticker="VZ",
        ex_dividend_date=date(2026, 4, 1),
        dividend_pay_date=date(2026, 4, 15),
    )
    preload = PortfolioAnalysisPreload(stock_data={}, yield_channels={}, vector_docs={})
    summary = service.build_summary([row], preload, reference_date=date(2026, 5, 13))
    assert summary.dividend_total == 0


def test_healthy_holding_not_flagged() -> None:
    service = PortfolioAttentionService()
    row = _row(ticker="JNJ", profit_pct=15.0, analyst_rating="BUY")
    preload = PortfolioAnalysisPreload(
        stock_data={},
        yield_channels={"JNJ": _yield_channel("Value")},
        vector_docs={},
    )
    summary = service.build_summary([row], preload, reference_date=date(2026, 5, 13))
    assert summary.total == 0
    assert summary.dividend_total == 0


def test_flags_value_zone_buy_opportunity() -> None:
    service = PortfolioAttentionService()
    row = _row(ticker="TGT", profit_pct=8.0, analyst_rating="BUY", growth_years=30)
    preload = PortfolioAnalysisPreload(
        stock_data={},
        yield_channels={"TGT": _yield_channel("Value")},
        vector_docs={},
    )
    summary = service.build_summary([row], preload, reference_date=date(2026, 5, 13))
    assert summary.total == 0
    assert summary.opportunity_total >= 1
    assert summary.high_count >= 1
    assert summary.opportunity_items[0].severity == "high"


def test_mild_red_zone_without_loss_not_high_risk() -> None:
    service = PortfolioAttentionService()
    row = _row(ticker="XOM", profit_pct=5.0, analyst_rating="HOLD")
    preload = PortfolioAnalysisPreload(
        stock_data={},
        yield_channels={"XOM": _yield_channel("Expensive")},
        vector_docs={},
    )
    summary = service.build_summary([row], preload, reference_date=date(2026, 5, 13))
    assert summary.total == 0
