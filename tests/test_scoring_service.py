"""Tests for score composition and dividend selection scoring behavior."""
# ruff: noqa: S101

from models.stock import DividendHistory, StockData
from services.scoring import ScoringService


def _stock(**overrides) -> StockData:
    base = StockData(
        symbol="KO",
        name="Coca-Cola",
        sector="Consumer Staples",
        industry="Beverages",
        dividend_yield_pct=3.2,
        payout_ratio_pct=58.0,
        dividend_coverage=1.9,
        dividend_history=DividendHistory(
            consecutive_years=25,
            total_years=30,
            cagr_5y=6.2,
            cagr_10y=5.1,
            current_annual=1.92,
        ),
        trailing_pe=20.0,
        price_to_52w_high_pct=-12.0,
        debt_to_equity=0.6,
        current_ratio=1.4,
        roe_pct=18.0,
        profit_margin_pct=21.0,
        market_cap=260e9,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_score_breakdown_sums_to_total() -> None:
    data = _stock()
    breakdown = ScoringService.calculate_score_breakdown(data)
    score = ScoringService.calculate_score(data)

    assert sum(item.points for item in breakdown) == score
    assert sum(item.max_points for item in breakdown) == 100


def test_very_high_yield_gets_no_yield_bonus() -> None:
    data = _stock(dividend_yield_pct=12.0)
    breakdown = ScoringService.calculate_score_breakdown(data)

    yield_component = next(item for item in breakdown if item.key == "yield")
    assert yield_component.points == 0
