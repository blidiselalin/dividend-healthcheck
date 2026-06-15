"""
Scoring and recommendation service.

This module calculates investment scores using a dividend-focused framework
emphasizing the key metrics that matter most to income investors.
"""

from dataclasses import dataclass

from config import RECOMMENDATION_THRESHOLDS
from models.stock import StockData


@dataclass(frozen=True)
class Recommendation:
    """Investment recommendation with supporting data.

    Attributes:
        label: Human-readable recommendation.
        emoji: Visual indicator.
        score: Numeric score (0-100).
        confidence: Data quality confidence (0-100).
    """

    label: str
    emoji: str
    score: int
    confidence: float = 100.0


@dataclass(frozen=True)
class ScoreComponent:
    """One score category contribution."""

    key: str
    label: str
    points: int
    max_points: int


class ScoringService:
    """Service for dividend-focused investment scoring.

    Scoring framework emphasizes:
    1. Dividend streak (consecutive years of increases)
    2. Dividend safety (payout ratio, coverage)
    3. Dividend yield (current income)
    4. Dividend growth (historical CAGR)
    5. Valuation & financial health
    """

    @staticmethod
    def calculate_score(data: StockData) -> int:
        """Calculate strategic investment score (0-100)."""
        total = sum(component.points for component in ScoringService.calculate_score_breakdown(data))
        return min(total, 100)

    @staticmethod
    def calculate_score_breakdown(data: StockData) -> list[ScoreComponent]:
        """Return category-level score contributions used in the total score."""
        components: list[ScoreComponent] = []

        streak_points = 0
        if data.dividend_history:
            years = data.dividend_history.consecutive_years
            if years >= 50:
                streak_points = 20
            elif years >= 40:
                streak_points = 18
            elif years >= 30:
                streak_points = 16
            elif years >= 25:
                streak_points = 14
            elif years >= 20:
                streak_points = 12
            elif years >= 15:
                streak_points = 10
            elif years >= 10:
                streak_points = 8
            elif years >= 5:
                streak_points = 5
            elif years >= 1:
                streak_points = 2
        components.append(
            ScoreComponent(
                key="streak",
                label="Dividend streak",
                points=streak_points,
                max_points=20,
            )
        )

        safety_points = 0
        if data.payout_ratio_pct is not None:
            pr = data.payout_ratio_pct
            if pr <= 40:
                safety_points += 10
            elif pr <= 50:
                safety_points += 9
            elif pr <= 60:
                safety_points += 8
            elif pr <= 70:
                safety_points += 6
            elif pr <= 80:
                safety_points += 4
            elif pr <= 100:
                safety_points += 2
        if data.dividend_coverage is not None:
            if data.dividend_coverage >= 3:
                safety_points += 5
            elif data.dividend_coverage >= 2:
                safety_points += 4
            elif data.dividend_coverage >= 1.5:
                safety_points += 3
            elif data.dividend_coverage >= 1.2:
                safety_points += 2
            elif data.dividend_coverage >= 1:
                safety_points += 1
        components.append(
            ScoreComponent(
                key="safety",
                label="Dividend safety",
                points=min(safety_points, 15),
                max_points=15,
            )
        )

        yield_points = 0
        if data.dividend_yield_pct is not None:
            dy = data.dividend_yield_pct
            if 2.5 <= dy <= 4.5:
                yield_points = 15
            elif 2.0 <= dy < 2.5 or 4.5 < dy <= 5.5:
                yield_points = 13
            elif 1.5 <= dy < 2.0 or 5.5 < dy <= 6.5:
                yield_points = 10
            elif 1.0 <= dy < 1.5 or 6.5 < dy <= 8.0:
                yield_points = 7
            elif 0.5 <= dy < 1.0 or 8.0 < dy <= 10:
                yield_points = 4
        components.append(
            ScoreComponent(
                key="yield",
                label="Dividend yield",
                points=yield_points,
                max_points=15,
            )
        )

        growth_points = 0
        if data.dividend_history:
            cagr = data.dividend_history.cagr_5y
            if cagr >= 10:
                growth_points = 15
            elif cagr >= 8:
                growth_points = 13
            elif cagr >= 6:
                growth_points = 11
            elif cagr >= 5:
                growth_points = 9
            elif cagr >= 4:
                growth_points = 7
            elif cagr >= 3:
                growth_points = 5
            elif cagr >= 2:
                growth_points = 3
            elif cagr > 0:
                growth_points = 1
        components.append(
            ScoreComponent(
                key="growth",
                label="Dividend growth",
                points=growth_points,
                max_points=15,
            )
        )

        valuation_points = 0
        pe = data.trailing_pe or data.forward_pe
        if pe and pe > 0:
            if pe <= 12:
                valuation_points += 6
            elif pe <= 15:
                valuation_points += 5
            elif pe <= 18:
                valuation_points += 4
            elif pe <= 22:
                valuation_points += 3
            elif pe <= 28:
                valuation_points += 2
            elif pe <= 35:
                valuation_points += 1
        if data.price_to_52w_high_pct is not None:
            off_high = abs(data.price_to_52w_high_pct)
            if off_high >= 20:
                valuation_points += 4
            elif off_high >= 10:
                valuation_points += 3
            elif off_high >= 5:
                valuation_points += 2
            else:
                valuation_points += 1
        components.append(
            ScoreComponent(
                key="valuation",
                label="Valuation",
                points=min(valuation_points, 10),
                max_points=10,
            )
        )

        strength_points = 0
        if data.debt_to_equity is not None:
            de = data.debt_to_equity
            if de <= 0.3:
                strength_points += 5
            elif de <= 0.5:
                strength_points += 4
            elif de <= 0.8:
                strength_points += 3
            elif de <= 1.2:
                strength_points += 2
            elif de <= 2.0:
                strength_points += 1
        if data.current_ratio:
            if data.current_ratio >= 2.0:
                strength_points += 5
            elif data.current_ratio >= 1.5:
                strength_points += 4
            elif data.current_ratio >= 1.2:
                strength_points += 3
            elif data.current_ratio >= 1.0:
                strength_points += 2
            elif data.current_ratio >= 0.8:
                strength_points += 1
        components.append(
            ScoreComponent(
                key="strength",
                label="Financial strength",
                points=min(strength_points, 10),
                max_points=10,
            )
        )

        profitability_points = 0
        if data.roe_pct is not None:
            if data.roe_pct >= 25:
                profitability_points += 5
            elif data.roe_pct >= 18:
                profitability_points += 4
            elif data.roe_pct >= 12:
                profitability_points += 3
            elif data.roe_pct >= 8:
                profitability_points += 2
            elif data.roe_pct >= 5:
                profitability_points += 1
        if data.profit_margin_pct is not None:
            if data.profit_margin_pct >= 20:
                profitability_points += 5
            elif data.profit_margin_pct >= 15:
                profitability_points += 4
            elif data.profit_margin_pct >= 10:
                profitability_points += 3
            elif data.profit_margin_pct >= 5:
                profitability_points += 2
            elif data.profit_margin_pct > 0:
                profitability_points += 1
        components.append(
            ScoreComponent(
                key="profitability",
                label="Profitability",
                points=min(profitability_points, 10),
                max_points=10,
            )
        )

        stability_points = 0
        if data.market_cap:
            if data.market_cap >= 100e9:
                stability_points = 5
            elif data.market_cap >= 50e9:
                stability_points = 4
            elif data.market_cap >= 10e9:
                stability_points = 3
            elif data.market_cap >= 2e9:
                stability_points = 2
            else:
                stability_points = 1
        components.append(
            ScoreComponent(
                key="stability",
                label="Size/stability",
                points=stability_points,
                max_points=5,
            )
        )

        return components

    @staticmethod
    def get_recommendation(score: int, confidence: float = 100.0) -> Recommendation:
        """Get recommendation based on score.

        Args:
            score: Investment score (0-100).
            confidence: Data quality confidence (0-100).

        Returns:
            Recommendation with label, emoji, score, and confidence.
        """
        thresholds = RECOMMENDATION_THRESHOLDS

        if score >= thresholds["strong_buy"]:
            return Recommendation("STRONG BUY", "🟢", score, confidence)
        if score >= thresholds["buy"]:
            return Recommendation("BUY", "🟡", score, confidence)
        if score >= thresholds["accumulate"]:
            return Recommendation("ACCUMULATE", "🟠", score, confidence)
        if score >= thresholds["hold"]:
            return Recommendation("HOLD", "⚪", score, confidence)
        return Recommendation("AVOID", "🔴", score, confidence)

    @staticmethod
    def get_investment_thesis(data: StockData) -> tuple[list[str], list[str]]:  # noqa: C901
        """Generate investment thesis with key strengths and concerns.

        Focuses on the metrics most important to dividend investors.
        """
        strengths: list[str] = []
        concerns: list[str] = []

        # === DIVIDEND STREAK (Most Important) ===
        if data.dividend_history:
            years = data.dividend_history.consecutive_years
            if years >= 50:
                strengths.append(f"🏆 Dividend King: {years} consecutive years of increases")
            elif years >= 25:
                strengths.append(f"👑 Dividend Aristocrat: {years} years of growth")
            elif years >= 10:
                strengths.append(f"✓ Proven track record: {years} years of increases")
            elif years < 5:
                concerns.append(f"Short dividend history ({years} years)")

        # === DIVIDEND YIELD ===
        if data.dividend_yield_pct is not None:
            if 2.5 <= data.dividend_yield_pct <= 5:
                strengths.append(f"Attractive yield ({data.dividend_yield_pct:.2f}%)")
            elif data.dividend_yield_pct >= 6:
                concerns.append(f"High yield may signal risk ({data.dividend_yield_pct:.2f}%)")
            elif data.dividend_yield_pct < 1.5:
                concerns.append(f"Low current yield ({data.dividend_yield_pct:.2f}%)")

        # === DIVIDEND SAFETY ===
        if data.payout_ratio_pct is not None:
            if data.payout_ratio_pct <= 50:
                strengths.append(f"Safe payout ratio ({data.payout_ratio_pct:.0f}%)")
            elif data.payout_ratio_pct >= 85:
                concerns.append(f"Elevated payout ratio ({data.payout_ratio_pct:.0f}%)")

        # === DIVIDEND GROWTH ===
        if data.dividend_history and data.dividend_history.cagr_5y >= 7:
            strengths.append(
                f"Strong dividend growth ({data.dividend_history.cagr_5y:.1f}% 5Y CAGR)"
            )
        elif data.dividend_history and data.dividend_history.cagr_5y < 3:
            concerns.append(f"Slow dividend growth ({data.dividend_history.cagr_5y:.1f}% 5Y CAGR)")

        # === VALUATION ===
        pe = data.trailing_pe
        if pe:
            if pe <= 15:
                strengths.append(f"Attractive valuation (P/E: {pe:.1f})")
            elif pe > 30:
                concerns.append(f"Expensive valuation (P/E: {pe:.1f})")

        # === FINANCIAL HEALTH ===
        if data.debt_to_equity is not None:
            if data.debt_to_equity <= 0.5:
                strengths.append("Low debt levels")
            elif data.debt_to_equity > 1.5:
                concerns.append(f"High debt (D/E: {data.debt_to_equity:.1f})")

        # === PROFITABILITY ===
        if data.roe_pct is not None:
            if data.roe_pct >= 18:
                strengths.append(f"High profitability (ROE: {data.roe_pct:.1f}%)")
            elif data.roe_pct < 8:
                concerns.append(f"Low profitability (ROE: {data.roe_pct:.1f}%)")

        return strengths, concerns
