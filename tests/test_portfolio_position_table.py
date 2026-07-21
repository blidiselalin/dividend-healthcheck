"""Home positions table service — concerns and dataframe shape."""

from __future__ import annotations

from datetime import date

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_position_table import (
    build_home_positions_dataframe,
    concerns_summary,
    position_concerns,
)


def _row(**overrides) -> PortfolioDetailRow:
    base = {
        "company": "Test Co",
        "ticker": "TST",
        "market_cap": None,
        "pe_ratio": None,
        "shares": 10.0,
        "current_price": 100.0,
        "current_value": 1000.0,
        "avg_cost_per_share": 90.0,
        "acquisition_value": 900.0,
        "profit": -100.0,
        "profit_pct": -10.0,
        "estimated_avg_price": 90.0,
        "medium_price_365d": None,
        "price_180d": None,
        "price_365d": None,
        "change_180d_pct": -12.0,
        "change_365d_pct": -18.0,
        "weight_pct": 5.0,
        "dividend_yield_pct": 10.5,
        "dividend_per_share": 1.0,
        "annual_income": 10.0,
        "dividend_weight_pct": 5.0,
        "income_weight_pct": 5.0,
        "dividends_paid": 0.0,
        "growth_years": 3,
        "commission": 0.0,
        "sector": "Technology",
        "acquisition_share_pct": 5.0,
        "analyst_rating": "Sell",
        "price_to_fcf": None,
        "computed_dividend": "Yes",
        "ex_dividend_date": date(2026, 6, 25),
        "dividend_pay_date": None,
        "data_source": "test",
        "previous_close": 102.0,
        "price_stale": True,
        "history_thin": True,
    }
    base.update(overrides)
    return PortfolioDetailRow(**base)


def test_position_concerns_collects_flags() -> None:
    concerns = position_concerns(
        _row(),
        risk_hint="Cut risk",
        today=date(2026, 6, 10),
    )
    assert "Stale price" in concerns
    assert "1Y price down" in concerns
    assert "High yield" in concerns
    assert len(concerns) >= 4


def test_build_home_positions_dataframe_columns() -> None:
    df = build_home_positions_dataframe([_row(ticker="KO", profit_pct=-5.0)])
    assert "Ticker" in df.columns
    assert "Concerns" in df.columns
    assert "P/L" in df.columns
    assert df.iloc[0]["Ticker"] == "KO"
    assert df.iloc[0]["P/L %"] == -5.0
    assert df.iloc[0]["P/L"] == 45.0


def test_concerns_summary_empty() -> None:
    assert concerns_summary([]) == "—"
