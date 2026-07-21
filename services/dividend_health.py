"""
Simple dividend health label from existing stock metrics (no new scoring engine).
"""

from __future__ import annotations

from dataclasses import dataclass

from config import PAYOUT_SAFE, PAYOUT_WATCH
from models.stock import StockData

HEALTH_HEALTHY = "Healthy"
HEALTH_WATCH = "Watch"
HEALTH_RISKY = "Risky"
HEALTH_UNKNOWN = "Not enough data"

DISCLAIMER = (
    "This is a simple research indicator based on available dividend and financial data. "
    "It is not financial advice."
)


@dataclass(frozen=True)
class DividendHealthResult:
    label: str
    reasons: tuple[str, ...]
    disclaimer: str = DISCLAIMER


def assess_dividend_health(data: StockData) -> DividendHealthResult:
    """Transparent rules using payout, growth, streak, safety, and yield only."""
    reasons: list[str] = []
    dh = data.dividend_history
    payout = data.payout_ratio_pct
    safety = data.dividend_safety_score
    yld = data.dividend_yield_pct
    cagr = dh.cagr_5y if dh else None
    streak = dh.consecutive_years if dh else None

    has_yield = yld is not None and yld > 0
    has_history = dh is not None and dh.total_years >= 2
    has_payout = payout is not None
    has_safety = safety is not None

    if not has_yield and not has_history and not has_payout:
        return DividendHealthResult(
            HEALTH_UNKNOWN,
            ("Insufficient dividend data in the shared library.",),
        )

    risky = False
    watch = False

    if payout is not None and payout > PAYOUT_WATCH:
        risky = True
        reasons.append(
            f"Payout ratio {payout:.0f}% is above the watch threshold ({PAYOUT_WATCH:.0f}%)."
        )
    elif payout is not None and payout > PAYOUT_SAFE:
        watch = True
        reasons.append(
            f"Payout ratio {payout:.0f}% leaves less room for raises "
            f"(watch above {PAYOUT_SAFE:.0f}%)."
        )

    if safety is not None and safety < 50:
        risky = True
        reasons.append(f"Dividend safety score {safety:.0f}/100 is low.")
    elif safety is not None and safety < 70:
        watch = True
        reasons.append(f"Dividend safety score {safety:.0f}/100 — monitor closely.")

    if cagr is not None and cagr < 0:
        risky = True
        reasons.append(f"5-year dividend growth is negative ({cagr:.1f}%).")
    elif cagr is not None and cagr < 2:
        watch = True
        reasons.append(f"5-year dividend growth is slow ({cagr:.1f}%).")

    if streak is not None and streak == 0 and has_history:
        watch = True
        reasons.append("No consecutive years of dividend increases in available history.")

    if yld is not None and yld >= 9:
        watch = True
        reasons.append(f"Yield {yld:.1f}% is unusually high — verify sustainability.")

    if data.dividend_coverage is not None and data.dividend_coverage < 1.0:
        risky = True
        reasons.append(f"EPS coverage {data.dividend_coverage:.1f}x is below 1×.")

    if risky:
        label = HEALTH_RISKY
    elif watch:
        label = HEALTH_WATCH
    elif has_yield or has_history or has_payout or has_safety:
        label = HEALTH_HEALTHY
        if not reasons:
            reasons.append(
                "Payout, growth, and safety metrics are within normal ranges for available data."
            )
    else:
        label = HEALTH_UNKNOWN
        reasons.append("Not enough dividend metrics to assess health.")

    return DividendHealthResult(label, tuple(reasons))
