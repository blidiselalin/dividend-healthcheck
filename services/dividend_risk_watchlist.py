"""
Build a Home dividend-risk watchlist from holdings + library StockData.

Pure logic (no Streamlit). Filters to Watch / Risky via assess_dividend_health.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from models.stock import StockData
from services.dividend_health import (
    HEALTH_RISKY,
    HEALTH_WATCH,
    assess_dividend_health,
)
from services.portfolio_details_service import PortfolioDetailRow

_SEVERITY_ORDER = {HEALTH_RISKY: 0, HEALTH_WATCH: 1}


@dataclass(frozen=True)
class DividendRiskWatchItem:
    ticker: str
    company: str
    yield_pct: float | None
    payout_pct: float | None
    fcf_payout_pct: float | None
    fcf_coverage_x: float | None
    safety_score: float | None
    safety_status: str
    reason: str
    weight_pct: float | None = None


def _fcf_coverage_multiple(fcf_payout_pct: float | None) -> float | None:
    if fcf_payout_pct is None or fcf_payout_pct <= 0:
        return None
    return round(100.0 / fcf_payout_pct, 2)


def _stock_for(
    ticker: str,
    stock_by_symbol: Mapping[str, StockData] | None,
) -> StockData | None:
    if not stock_by_symbol:
        return None
    return stock_by_symbol.get(ticker) or stock_by_symbol.get(ticker.upper())


def build_dividend_risk_watchlist(
    rows: Sequence[PortfolioDetailRow],
    stock_by_symbol: Mapping[str, StockData] | None = None,
    *,
    include_healthy: bool = False,
) -> list[DividendRiskWatchItem]:
    """
    Return Watch/Risky holdings with yield, payout, FCF, and safety status.

    When include_healthy is False (default), Healthy / unknown names are omitted.
    """
    items: list[DividendRiskWatchItem] = []
    for row in rows:
        if row.shares is not None and row.shares <= 0:
            continue
        stock = _stock_for(row.ticker, stock_by_symbol)
        if stock is None:
            # Minimal stub so health can still flag high yield from the row.
            stock = StockData(
                symbol=row.ticker,
                name=row.company or row.ticker,
                sector="",
                industry="",
                dividend_yield_pct=row.dividend_yield_pct,
            )
        health = assess_dividend_health(stock)
        if not include_healthy and health.label not in (HEALTH_RISKY, HEALTH_WATCH):
            continue

        yield_pct = row.dividend_yield_pct
        if yield_pct is None:
            yield_pct = stock.dividend_yield_pct
        payout = stock.payout_ratio_pct
        fcf_payout = stock.fcf_payout_ratio_pct
        reason = health.reasons[0] if health.reasons else health.label

        items.append(
            DividendRiskWatchItem(
                ticker=row.ticker.upper(),
                company=(row.company or stock.name or row.ticker).strip(),
                yield_pct=yield_pct,
                payout_pct=payout,
                fcf_payout_pct=fcf_payout,
                fcf_coverage_x=_fcf_coverage_multiple(fcf_payout),
                safety_score=stock.dividend_safety_score,
                safety_status=health.label,
                reason=reason,
                weight_pct=row.weight_pct,
            )
        )

    items.sort(
        key=lambda item: (
            _SEVERITY_ORDER.get(item.safety_status, 9),
            -(item.payout_pct or -1.0),
            -(item.yield_pct or -1.0),
            item.ticker,
        )
    )
    return items


def watchlist_counts(items: Sequence[DividendRiskWatchItem]) -> dict[str, int]:
    risky = sum(1 for item in items if item.safety_status == HEALTH_RISKY)
    watch = sum(1 for item in items if item.safety_status == HEALTH_WATCH)
    return {"risky": risky, "watch": watch, "total": len(items)}


def watchlist_to_records(items: Sequence[DividendRiskWatchItem]) -> list[dict[str, Any]]:
    """Rows suitable for a Streamlit dataframe."""
    records: list[dict[str, Any]] = []
    for item in items:
        records.append(
            {
                "Ticker": item.ticker,
                "Company": item.company,
                "Yield %": item.yield_pct,
                "Payout %": item.payout_pct,
                "FCF payout %": item.fcf_payout_pct,
                "FCF coverage": item.fcf_coverage_x,
                "Safety score": item.safety_score,
                "Safety": item.safety_status,
                "Why": item.reason,
            }
        )
    return records
