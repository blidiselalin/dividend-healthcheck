"""
Helpers for adaptive yield-channel history windows (2-10 years).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def _collect_history_dates(document: Any) -> list[date]:
    dates: list[date] = []
    if document is None:
        return dates
    for point in getattr(document, "price_history", None) or []:
        raw = getattr(point, "date", None)
        if raw is not None:
            dates.append(raw)
    for record in getattr(document, "dividend_history", None) or []:
        raw = getattr(record, "ex_date", None)
        if raw is not None:
            dates.append(raw)
    return dates


def estimate_history_years(document: Any, *, minimum: int = 1) -> int | None:
    """Calendar years spanned by library price/dividend history."""
    dates = _collect_history_dates(document)
    if not dates:
        return None
    span_days = (max(dates) - min(dates)).days
    if span_days <= 0:
        return minimum
    return max(minimum, round(span_days / 365.25))


def years_covered_by_frame(hist: pd.DataFrame) -> int:
    """Years between first and last row in a prepared price/yield frame."""
    if hist is None or hist.empty:
        return 0
    start = pd.Timestamp(hist.index.min())
    end = pd.Timestamp(hist.index.max())
    days = max(0, (end - start).days)
    return max(1, round(days / 365.25))


def plan_yield_channel_attempts(
    document: Any,
    *,
    requested_years: int = 10,
) -> list[tuple[int, int, int]]:
    """
    Return (years, min_price_rows, min_yield_rows) attempts from richest to leanest.

    Uses up to ``requested_years`` when the library has enough span; otherwise tries
    shorter windows so newer payers still get a chart.
    """
    available = estimate_history_years(document)
    year_candidates: list[int] = []
    for years in (requested_years, 7, 5, 3, 2):
        if years < 2:
            continue
        if available is None or years <= available + 1:
            year_candidates.append(years)
    if not year_candidates:
        year_candidates = [requested_years, 5, 3, 2]

    attempts: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for years in year_candidates:
        for min_prices, min_yields in ((120, 60), (52, 26), (52, 13)):
            key = (years, min_prices, min_yields)
            if key in seen:
                continue
            seen.add(key)
            attempts.append(key)
    return attempts


def yield_channel_history_label(years_analyzed: int, *, requested: int = 10) -> str:
    """Human label for chart headers when history is shorter than 10Y."""
    if years_analyzed >= requested:
        return f"{years_analyzed}-year"
    if years_analyzed >= 2:
        return f"{years_analyzed}-year (available history)"
    return "short-term"
