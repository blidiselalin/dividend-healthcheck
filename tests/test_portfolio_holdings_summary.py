"""Tests for portfolio holdings summary aggregation."""
# ruff: noqa: S101

from __future__ import annotations

from typing import Any

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_holdings_summary import compute_holdings_summary


def _row(**overrides: Any) -> PortfolioDetailRow:
    base = {
        "company": "Test Co",
        "ticker": "TST",
        "market_cap": 5_000_000_000,
        "pe_ratio": 15.0,
        "shares": 100.0,
        "current_price": 650.0,
        "current_value": 65000.0,
        "avg_cost_per_share": 540.0,
        "acquisition_value": 54000.0,
        "profit": 11000.0,
        "profit_pct": 20.37,
        "estimated_avg_price": 540.0,
        "medium_price_365d": 95.0,
        "price_180d": 98.0,
        "price_365d": 90.0,
        "change_180d_pct": 2.0,
        "change_365d_pct": 11.0,
        "weight_pct": 50.0,
        "dividend_yield_pct": 3.0,
        "dividend_per_share": 3.0,
        "annual_income": 300.0,
        "dividend_weight_pct": 5.0,
        "income_weight_pct": 5.0,
        "dividends_paid": 0.0,
        "growth_years": 10,
        "commission": 0.0,
        "sector": "Technology",
        "acquisition_share_pct": 50.0,
        "analyst_rating": "BUY",
        "price_to_fcf": 10.0,
        "computed_dividend": "3.00 (3.00%)",
        "ex_dividend_date": None,
        "dividend_pay_date": None,
        "data_source": "test",
        "previous_close": 645.0,
    }
    base.update(overrides)
    return PortfolioDetailRow(**base)


def test_compute_holdings_summary_totals() -> None:
    rows = [
        _row(
            ticker="INTU",
            shares=100.0,
            current_price=650.0,
            current_value=65000.0,
            acquisition_value=54000.0,
            previous_close=645.0,
        ),
        _row(
            ticker="KO",
            shares=200.0,
            current_price=62.0,
            current_value=12400.0,
            acquisition_value=11000.0,
            previous_close=61.5,
        ),
    ]
    summary = compute_holdings_summary(rows)

    assert summary.total_value_usd == 77400.0
    assert summary.unrealized_gl_usd == 12400.0
    assert summary.unrealized_gl_pct == 19.08
    assert summary.day_change_usd == 600.0
    assert summary.day_change_pct == 0.78


def test_day_change_missing_when_no_previous_close() -> None:
    summary = compute_holdings_summary([_row(previous_close=None)])
    assert summary.day_change_usd is None
    assert summary.day_change_pct is None
    assert summary.unrealized_gl_usd == 11000.0


def test_empty_rows_summary() -> None:
    summary = compute_holdings_summary([])
    assert summary.positions == 0
    assert summary.total_value_usd == 0.0
    assert summary.day_change_usd is None


def test_partial_previous_close_excludes_missing_symbols() -> None:
    rows = [
        _row(
            ticker="A",
            previous_close=100.0,
            current_price=101.0,
            shares=10.0,
            current_value=1010.0,
        ),
        _row(
            ticker="B",
            previous_close=None,
            current_price=50.0,
            shares=10.0,
            current_value=500.0,
        ),
    ]
    summary = compute_holdings_summary(rows)
    assert summary.day_change_usd == 10.0
    assert summary.day_change_pct == 1.0
