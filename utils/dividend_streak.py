"""Utilities for dividend streak calculations."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any


def annualize_year_payments(payments: Sequence[float]) -> float:
    """Estimate a regular annual dividend from payments in a calendar year."""
    positive = [payment for payment in payments if payment > 0]
    if not positive:
        return 0.0

    median_payment = statistics.median(positive)
    payment_count = len(positive)
    if payment_count >= 11:
        return 12 * median_payment
    if payment_count >= 3:
        return 4 * median_payment
    if payment_count == 2:
        return 2 * median_payment
    return float(sum(positive))


def annual_totals_from_payments(
    year_to_payments: Mapping[int, Sequence[float]],
) -> dict[int, float]:
    """Convert per-year payment lists into normalized annual dividend totals."""
    return {year: annualize_year_payments(payments) for year, payments in year_to_payments.items()}


def calculate_consecutive_increase_years(
    annual_totals: Mapping[int, float],
    *,
    reference_date: date | None = None,
) -> int:
    """Count consecutive years of maintained or increased annual dividends."""
    if not annual_totals:
        return 0

    years = sorted(year for year, total in annual_totals.items() if total > 0)
    if len(years) < 2:
        return 0

    current_year = (reference_date or date.today()).year
    if years[-1] == current_year:
        years = years[:-1]

    if len(years) < 2:
        return 0

    streak = 0
    for index in range(len(years) - 1, 0, -1):
        current_total = annual_totals[years[index]]
        prior_total = annual_totals[years[index - 1]]
        if prior_total <= 0 or current_total < prior_total:
            break
        streak += 1

    return streak


def resolve_consecutive_years(
    *,
    curated_years: int | None = None,
    annual_totals: Mapping[int, float] | None = None,
    reference_date: date | None = None,
) -> int:
    """Prefer curated streak data and never downgrade below computed history."""
    computed = (
        calculate_consecutive_increase_years(
            annual_totals,
            reference_date=reference_date,
        )
        if annual_totals
        else 0
    )
    if curated_years is None:
        return computed
    if computed <= 0:
        return curated_years
    return max(curated_years, computed)


def apply_dividend_streak_to_document(doc: Any) -> None:
    """Refresh dividend_streak_years from curated data and payment history."""
    curated = doc.dividend_streak_years
    records = doc.dividend_history
    if not records and curated is None:
        doc.dividend_streak_years = 0
        return

    year_to_payments: dict[int, list[float]] = {}
    for record in records or []:
        year_to_payments.setdefault(record.ex_date.year, []).append(record.amount)

    annual_totals = annual_totals_from_payments(year_to_payments) if year_to_payments else None
    doc.dividend_streak_years = resolve_consecutive_years(
        curated_years=curated,
        annual_totals=annual_totals,
    )
