"""Integration tests for high-risk watchlist pipeline and session wiring."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.portfolio_analysis_preload import PortfolioAnalysisPreload
from services.portfolio_attention_service import PortfolioAttentionService
from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_risk_monitor_service import PortfolioRiskMonitorService
from services.yield_channel_chart import YieldChannelData
from ui.portfolio_risk_panel import (
    SESSION_SUMMARY_KEY,
    get_cached_attention_summary,
    refresh_portfolio_risks,
)


def _row(**overrides: Any) -> PortfolioDetailRow:
    base = {
        "company": "Test Co",
        "ticker": "ARE",
        "market_cap": 1e9,
        "pe_ratio": 15.0,
        "shares": 10.0,
        "current_price": 100.0,
        "current_value": 1000.0,
        "avg_cost_per_share": 120.0,
        "acquisition_value": 1200.0,
        "profit": -200.0,
        "profit_pct": -22.0,
        "estimated_avg_price": 120.0,
        "medium_price_365d": 95.0,
        "price_180d": 98.0,
        "price_365d": 90.0,
        "change_180d_pct": 2.0,
        "change_365d_pct": 11.0,
        "weight_pct": 9.5,
        "dividend_yield_pct": 3.0,
        "dividend_per_share": 3.0,
        "annual_income": 30.0,
        "dividend_weight_pct": 5.0,
        "income_weight_pct": 5.0,
        "dividends_paid": 0.0,
        "growth_years": 10,
        "commission": 0.0,
        "sector": "Tech",
        "acquisition_share_pct": 9.5,
        "analyst_rating": "AVOID",
        "price_to_fcf": 10.0,
        "computed_dividend": "3.00 (3.00%)",
        "ex_dividend_date": None,
        "dividend_pay_date": None,
        "data_source": "test",
    }
    base.update(overrides)
    return PortfolioDetailRow(**base)


def _yield_channel(zone: str = "Expensive") -> YieldChannelData:
    return YieldChannelData(
        symbol="ARE",
        company_name="Alexandria",
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


def test_risk_monitor_build_summary_flags_high_risk_holding() -> None:
    monitor = PortfolioRiskMonitorService()
    row = _row()
    preload = PortfolioAnalysisPreload(
        stock_data={},
        yield_channels={"ARE": _yield_channel("Expensive")},
        vector_docs={},
    )

    summary = monitor.build_summary([row], preload, reference_date=date(2026, 5, 13))

    assert summary.total >= 1
    assert summary.risk_items[0].symbol == "ARE"
    assert "Exposure" in summary.risk_items[0].categories


def test_refresh_portfolio_risks_persists_session_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    session: dict = {}
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    row = _row()
    preload = PortfolioAnalysisPreload(
        stock_data={},
        yield_channels={"ARE": _yield_channel("Expensive")},
        vector_docs={},
    )

    summary = refresh_portfolio_risks(force=True, rows=[row], preload=preload)

    assert summary is not None
    assert summary.total >= 1
    assert SESSION_SUMMARY_KEY in session
    cached = get_cached_attention_summary()
    assert cached is not None
    assert cached.total >= 1


def test_refresh_portfolio_risks_uses_session_without_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-force refresh must not call build_rows_with_cache when session has rows."""
    from ui.portfolio_risk_panel import SESSION_SUMMARY_KEY, refresh_portfolio_risks

    row = _row()
    preload = PortfolioAnalysisPreload(
        stock_data={},
        yield_channels={"ARE": _yield_channel("Expensive")},
        vector_docs={},
    )
    session = {
        "portfolio_details_rows": [row],
        "portfolio_stock_cache": preload.stock_data,
        "portfolio_yield_cache": preload.yield_channels,
        "portfolio_vector_docs": preload.vector_docs,
    }
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    build_calls: list[bool] = []

    def _forbidden_build(*args, **kwargs):
        build_calls.append(True)
        raise AssertionError("build_rows_with_cache should not run")

    monkeypatch.setattr(
        "services.portfolio_details_service.PortfolioDetailsService.build_rows_with_cache",
        _forbidden_build,
    )

    summary = refresh_portfolio_risks(force=False)

    assert summary is not None
    assert summary.total >= 1
    assert SESSION_SUMMARY_KEY in session
    assert build_calls == []


def test_apply_yield_preload_rebuilds_risk_watchlist(monkeypatch: pytest.MonkeyPatch) -> None:
    session: dict = {
        "portfolio_details_rows": [_row()],
        "portfolio_stock_cache": {},
        "portfolio_yield_cache": {"ARE": _yield_channel("Expensive")},
        "portfolio_vector_docs": {},
    }
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    from services.deferred_startup import _apply_yield_preload

    with patch("services.portfolio_ui_cache.save_session_cache"):
        _apply_yield_preload(
            {
                "yield_channels": {"ARE": _yield_channel("Expensive")},
                "stock_data": {},
                "vector_docs": {},
            }
        )

    assert session.get("portfolio_analysis_ready") is True
    assert SESSION_SUMMARY_KEY in session
    cached = get_cached_attention_summary()
    assert cached is not None
    assert cached.total >= 1


def test_portfolio_details_view_imports_refresh_portfolio_risks() -> None:
    import ui.portfolio_details_view as view

    assert callable(view.refresh_portfolio_risks)


def test_monitor_include_news_only_for_risk_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    attention = PortfolioAttentionService()
    monitor = PortfolioRiskMonitorService(attention=attention)
    row = _row(ticker="ARE")
    preload = PortfolioAnalysisPreload(
        stock_data={},
        yield_channels={"ARE": _yield_channel("Expensive")},
        vector_docs={},
    )

    news = MagicMock(overall_sentiment="bearish", sentiment_score=-0.5)
    with patch.object(
        PortfolioAttentionService,
        "fetch_news_for_symbols",
        return_value={"ARE": news},
    ) as fetch_news:
        summary = monitor.build_summary(
            [row],
            preload,
            reference_date=date(2026, 5, 13),
            include_news=True,
        )

    assert summary.total >= 1
    fetch_news.assert_called_once()
    assert fetch_news.call_args[0][0] == ["ARE"]
