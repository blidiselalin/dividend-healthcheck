"""Tests for Home dividend risk watchlist builder."""

from __future__ import annotations

from models.stock import StockData
from services.dividend_health import HEALTH_HEALTHY, HEALTH_RISKY, HEALTH_WATCH
from services.dividend_risk_watchlist import (
    build_dividend_risk_watchlist,
    watchlist_counts,
    watchlist_to_records,
)
from services.portfolio_details_service import PortfolioDetailRow


def _row(
    ticker: str,
    *,
    yield_pct: float | None = 3.0,
    company: str = "Test Co",
) -> PortfolioDetailRow:
    return PortfolioDetailRow(
        company=company,
        ticker=ticker,
        market_cap=1e9,
        pe_ratio=15.0,
        shares=10.0,
        current_price=100.0,
        current_value=1000.0,
        avg_cost_per_share=90.0,
        acquisition_value=900.0,
        profit=100.0,
        profit_pct=11.0,
        estimated_avg_price=90.0,
        medium_price_365d=95.0,
        price_180d=98.0,
        price_365d=90.0,
        change_180d_pct=2.0,
        change_365d_pct=11.0,
        weight_pct=5.0,
        dividend_yield_pct=yield_pct,
        dividend_per_share=3.0,
        annual_income=30.0,
        dividend_weight_pct=5.0,
        income_weight_pct=5.0,
        dividends_paid=0.0,
        growth_years=10,
        commission=0.0,
        sector="Tech",
        acquisition_share_pct=5.0,
        analyst_rating="BUY",
        price_to_fcf=10.0,
        computed_dividend="3.00 (3.00%)",
        ex_dividend_date=None,
        dividend_pay_date=None,
        data_source="test",
    )


def test_watchlist_includes_risky_and_watch_only() -> None:
    stocks = {
        "RISK": StockData(
            symbol="RISK",
            name="Risky Inc",
            sector="Utilities",
            industry="Electric",
            dividend_yield_pct=4.0,
            payout_ratio_pct=110.0,
            fcf_payout_ratio_pct=130.0,
        ),
        "WATCH": StockData(
            symbol="WATCH",
            name="Watch Co",
            sector="Consumer",
            industry="Beverages",
            dividend_yield_pct=3.5,
            payout_ratio_pct=70.0,
            fcf_payout_ratio_pct=55.0,
        ),
        "OK": StockData(
            symbol="OK",
            name="Healthy Co",
            sector="Tech",
            industry="Software",
            dividend_yield_pct=1.5,
            payout_ratio_pct=30.0,
            fcf_payout_ratio_pct=25.0,
        ),
    }
    items = build_dividend_risk_watchlist(
        [_row("RISK"), _row("WATCH"), _row("OK")],
        stocks,
    )
    tickers = [item.ticker for item in items]
    assert tickers == ["RISK", "WATCH"]
    assert items[0].safety_status == HEALTH_RISKY
    assert items[1].safety_status == HEALTH_WATCH
    assert items[0].fcf_coverage_x == round(100 / 130, 2)


def test_watchlist_counts_and_records() -> None:
    stocks = {
        "RISK": StockData(
            symbol="RISK",
            name="Risky Inc",
            sector="Utilities",
            industry="Electric",
            payout_ratio_pct=120.0,
            dividend_yield_pct=6.0,
        ),
    }
    items = build_dividend_risk_watchlist([_row("RISK")], stocks)
    counts = watchlist_counts(items)
    assert counts["risky"] == 1
    assert counts["total"] == 1
    records = watchlist_to_records(items)
    assert records[0]["Ticker"] == "RISK"
    assert "Payout %" in records[0]
    assert "FCF coverage" in records[0]


def test_include_healthy_optional() -> None:
    stocks = {
        "OK": StockData(
            symbol="OK",
            name="Healthy Co",
            sector="Tech",
            industry="Software",
            dividend_yield_pct=1.5,
            payout_ratio_pct=30.0,
        ),
    }
    items = build_dividend_risk_watchlist([_row("OK")], stocks, include_healthy=True)
    assert len(items) == 1
    assert items[0].safety_status == HEALTH_HEALTHY
