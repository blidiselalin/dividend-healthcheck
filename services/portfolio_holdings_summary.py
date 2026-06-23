"""
Portfolio-wide holdings summary — total value, day change, unrealized gain/loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.portfolio_details_service import PortfolioDetailRow


@dataclass(frozen=True)
class HoldingsSummary:
    """Top-line portfolio KPIs shown on the home and holdings views."""

    positions: int
    total_value_usd: float
    acquisition_value_usd: float
    day_change_usd: float | None
    day_change_pct: float | None
    unrealized_gl_usd: float
    unrealized_gl_pct: float | None


def compute_holdings_summary(rows: list[PortfolioDetailRow]) -> HoldingsSummary:
    """Aggregate current value, day change, and unrealized P/L from detail rows."""
    total_value = sum(row.current_value or 0.0 for row in rows)
    total_acquisition = sum(row.acquisition_value for row in rows)
    unrealized = total_value - total_acquisition
    unrealized_pct = (unrealized / total_acquisition * 100) if total_acquisition > 0 else None

    prior_value = 0.0
    day_change = 0.0
    has_day_change = False
    for row in rows:
        if row.current_price is None or row.previous_close is None:
            continue
        prior_value += row.shares * row.previous_close
        day_change += row.shares * (row.current_price - row.previous_close)
        has_day_change = True

    day_change_usd = day_change if has_day_change else None
    day_change_pct = (
        (day_change / prior_value * 100) if has_day_change and prior_value > 0 else None
    )

    return HoldingsSummary(
        positions=len(rows),
        total_value_usd=round(total_value, 2),
        acquisition_value_usd=round(total_acquisition, 2),
        day_change_usd=round(day_change_usd, 2) if day_change_usd is not None else None,
        day_change_pct=round(day_change_pct, 2) if day_change_pct is not None else None,
        unrealized_gl_usd=round(unrealized, 2),
        unrealized_gl_pct=round(unrealized_pct, 2) if unrealized_pct is not None else None,
    )


def sort_positions_worst_first(rows: list[PortfolioDetailRow]) -> list[PortfolioDetailRow]:
    """Sort by unrealized P/L % ascending — losses and laggards surface first."""

    def _sort_key(row: PortfolioDetailRow) -> tuple[int, float]:
        if row.profit_pct is None:
            return (1, 0.0)
        return (0, row.profit_pct)

    return sorted(rows, key=_sort_key)
