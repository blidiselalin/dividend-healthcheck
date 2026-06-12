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
    def calculate_score(data: StockData) -> int:  # noqa: C901
        """Calculate strategic investment score (0-100).

        Weights:
        - Dividend Streak: 20 pts
        - Dividend Safety: 15 pts
        - Dividend Yield: 15 pts
        - Dividend Growth: 15 pts
        - Valuation: 10 pts
        - Financial Strength: 10 pts
        - Profitability: 10 pts
        - Size/Stability: 5 pts
        """
        score = 0

        # === DIVIDEND STREAK (20 points) ===
        # The defining characteristic of Dividend Kings
        if data.dividend_history:
            years = data.dividend_history.consecutive_years
            if years >= 50:
                score += 20  # True Dividend King
            elif years >= 40:
                score += 18
            elif years >= 30:
                score += 16
            elif years >= 25:
                score += 14  # Aristocrat
            elif years >= 20:
                score += 12
            elif years >= 15:
                score += 10
            elif years >= 10:
                score += 8  # Achiever
            elif years >= 5:
                score += 5  # Contender
            elif years >= 1:
                score += 2

        # === DIVIDEND SAFETY (15 points) ===
        # Payout ratio - lower is safer
        if data.payout_ratio_pct is not None:
            pr = data.payout_ratio_pct
            if pr <= 40:
                score += 10
            elif pr <= 50:
                score += 9
            elif pr <= 60:
                score += 8
            elif pr <= 70:
                score += 6
            elif pr <= 80:
                score += 4
            elif pr <= 100:
                score += 2
            # >100% is risky, 0 points

        # Dividend coverage (EPS/DPS) - higher is safer
        if data.dividend_coverage is not None:
            if data.dividend_coverage >= 3:
                score += 5
            elif data.dividend_coverage >= 2:
                score += 4
            elif data.dividend_coverage >= 1.5:
                score += 3
            elif data.dividend_coverage >= 1.2:
                score += 2
            elif data.dividend_coverage >= 1:
                score += 1

        # === DIVIDEND YIELD (15 points) ===
        # Sweet spot is 2-5% - not too low, not suspiciously high
        if data.dividend_yield_pct is not None:
            dy = data.dividend_yield_pct
            if 2.5 <= dy <= 4.5:
                score += 15  # Optimal range
            elif 2.0 <= dy < 2.5 or 4.5 < dy <= 5.5:
                score += 13
            elif 1.5 <= dy < 2.0 or 5.5 < dy <= 6.5:
                score += 10
            elif 1.0 <= dy < 1.5 or 6.5 < dy <= 8.0:
                score += 7
            elif dy >= 0.5 or 8.0 < dy <= 10:
                score += 4
            # Very high yields (>10%) often signal risk

        # === DIVIDEND GROWTH (15 points) ===
        # Historical CAGR indicates future growth potential
        if data.dividend_history:
            # Use 5-year CAGR primarily
            cagr = data.dividend_history.cagr_5y
            if cagr >= 10:
                score += 15
            elif cagr >= 8:
                score += 13
            elif cagr >= 6:
                score += 11
            elif cagr >= 5:
                score += 9
            elif cagr >= 4:
                score += 7
            elif cagr >= 3:
                score += 5
            elif cagr >= 2:
                score += 3
            elif cagr > 0:
                score += 1

        # === VALUATION (10 points) ===
        # P/E ratio assessment
        pe = data.trailing_pe or data.forward_pe
        if pe and pe > 0:
            if pe <= 12:
                score += 6
            elif pe <= 15:
                score += 5
            elif pe <= 18:
                score += 4
            elif pe <= 22:
                score += 3
            elif pe <= 28:
                score += 2
            elif pe <= 35:
                score += 1

        # Price vs 52-week high (buying opportunity indicator)
        if data.price_to_52w_high_pct is not None:
            off_high = abs(data.price_to_52w_high_pct)
            if off_high >= 20:
                score += 4  # Significant discount
            elif off_high >= 10:
                score += 3
            elif off_high >= 5:
                score += 2
            else:
                score += 1  # Near high

        # === FINANCIAL STRENGTH (10 points) ===
        # Debt-to-Equity
        if data.debt_to_equity is not None:
            de = data.debt_to_equity
            if de <= 0.3:
                score += 5
            elif de <= 0.5:
                score += 4
            elif de <= 0.8:
                score += 3
            elif de <= 1.2:
                score += 2
            elif de <= 2.0:
                score += 1

        # Liquidity (Current Ratio)
        if data.current_ratio:
            if data.current_ratio >= 2.0:
                score += 5
            elif data.current_ratio >= 1.5:
                score += 4
            elif data.current_ratio >= 1.2:
                score += 3
            elif data.current_ratio >= 1.0:
                score += 2
            elif data.current_ratio >= 0.8:
                score += 1

        # === PROFITABILITY (10 points) ===
        # ROE
        if data.roe_pct is not None:
            if data.roe_pct >= 25:
                score += 5
            elif data.roe_pct >= 18:
                score += 4
            elif data.roe_pct >= 12:
                score += 3
            elif data.roe_pct >= 8:
                score += 2
            elif data.roe_pct >= 5:
                score += 1

        # Profit Margins
        if data.profit_margin_pct is not None:
            if data.profit_margin_pct >= 20:
                score += 5
            elif data.profit_margin_pct >= 15:
                score += 4
            elif data.profit_margin_pct >= 10:
                score += 3
            elif data.profit_margin_pct >= 5:
                score += 2
            elif data.profit_margin_pct > 0:
                score += 1

        # === SIZE/STABILITY (5 points) ===
        if data.market_cap:
            if data.market_cap >= 100e9:
                score += 5  # Mega cap
            elif data.market_cap >= 50e9:
                score += 4  # Large cap
            elif data.market_cap >= 10e9:
                score += 3  # Mid-large
            elif data.market_cap >= 2e9:
                score += 2  # Mid cap
            else:
                score += 1  # Small cap

        return min(score, 100)

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
