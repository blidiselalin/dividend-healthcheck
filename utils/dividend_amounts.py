"""
Canonical dividend amount and frequency helpers.

Used by portfolio details (annual income) and the monthly dividend calendar
(per-payment cash) so both views stay consistent.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, List, Optional, Sequence

if TYPE_CHECKING:
    from data_ingestion.models import DividendRecord, StockDocument
    from models.stock import StockData

FREQUENCY_MONTHLY = 12
FREQUENCY_QUARTERLY = 4
FREQUENCY_SEMI_ANNUAL = 2
FREQUENCY_ANNUAL = 1

MONTHLY_THRESHOLD = 10
QUARTERLY_THRESHOLD = 3.5
SEMI_ANNUAL_THRESHOLD = 1.5


def payments_per_year(
    records: Sequence["DividendRecord"],
    *,
    stored_frequency: Optional[int] = None,
) -> int:
    """Payments per year from history; prefer detected over stale stored value."""
    if records:
        detected = detect_payment_frequency(records)
        if stored_frequency and stored_frequency in (1, 2, 4, 12):
            if stored_frequency == detected:
                return stored_frequency
            # Stored frequency often wrong (e.g. monthly REITs saved as quarterly).
            if stored_frequency == FREQUENCY_QUARTERLY and detected == FREQUENCY_MONTHLY:
                return detected
            if abs(stored_frequency - detected) <= 1:
                return detected
        return detected
    if stored_frequency in (1, 2, 4, 12):
        return stored_frequency
    return FREQUENCY_QUARTERLY


def detect_payment_frequency(dividend_history: Sequence["DividendRecord"]) -> int:
    """
    Detect dividend payment frequency from recent complete calendar years.

    Using only the last few years avoids misclassifying long-run monthly payers
    (e.g. O) as quarterly when older history had fewer entries per year.
    """
    if not dividend_history or len(dividend_history) < 2:
        return FREQUENCY_QUARTERLY

    today = date.today()
    years_count: dict[int, int] = {}
    for div in dividend_history:
        year = div.ex_date.year
        years_count[year] = years_count.get(year, 0) + 1

    if not years_count:
        return FREQUENCY_QUARTERLY

    complete_years = sorted(y for y in years_count if y < today.year)
    if not complete_years:
        complete_years = sorted(years_count)

    recent_years = complete_years[-3:]
    avg_per_year = sum(years_count[y] for y in recent_years) / len(recent_years)

    if avg_per_year >= MONTHLY_THRESHOLD:
        return FREQUENCY_MONTHLY
    if avg_per_year >= QUARTERLY_THRESHOLD:
        return FREQUENCY_QUARTERLY
    if avg_per_year >= SEMI_ANNUAL_THRESHOLD:
        return FREQUENCY_SEMI_ANNUAL
    return FREQUENCY_ANNUAL


def trailing_annual_dividend(
    records: Sequence["DividendRecord"],
    *,
    frequency: Optional[int] = None,
) -> Optional[float]:
    """Sum of the last N per-share payments (N = payments per year)."""
    if not records:
        return None
    freq = frequency or detect_payment_frequency(records)
    ordered = sorted(records, key=lambda record: record.ex_date)
    window = ordered[-freq:]
    if not window:
        return None
    return round(sum(record.amount for record in window), 4)


def latest_payment_amount(records: Sequence["DividendRecord"]) -> Optional[float]:
    if not records:
        return None
    recent = max(records, key=lambda record: record.ex_date)
    return float(recent.amount)


def resolve_annual_dividend_per_share(
    records: Sequence["DividendRecord"],
    document: Optional["StockDocument"] = None,
    stock: Optional["StockData"] = None,
) -> Optional[float]:
    """
    Best estimate of annual dividend per share.

    Prefers trailing payments from history, then document/stock annual fields.
    """
    stored_freq = None
    if document and document.payment_frequency:
        stored_freq = document.payment_frequency

    ttm = trailing_annual_dividend(records, frequency=payments_per_year(records, stored_frequency=stored_freq))
    candidates: List[float] = []
    if ttm is not None and ttm > 0:
        candidates.append(ttm)

    if document and document.annual_dividend and document.annual_dividend > 0:
        candidates.append(float(document.annual_dividend))
    if stock and stock.dividend_rate and stock.dividend_rate > 0:
        candidates.append(float(stock.dividend_rate))
    if stock and stock.dividend_history and stock.dividend_history.current_annual > 0:
        candidates.append(float(stock.dividend_history.current_annual))

    if not candidates:
        return None

    if ttm is not None and ttm > 0:
        for value in candidates[1:]:
            if abs(value - ttm) / ttm <= 0.2:
                return round(ttm, 4)
        return round(ttm, 4)

    return round(max(candidates), 4)


def per_payment_amount(
    records: Sequence["DividendRecord"],
    document: Optional["StockDocument"] = None,
    stock: Optional["StockData"] = None,
) -> Optional[float]:
    """Cash dividend per payment (not annualized)."""
    latest = latest_payment_amount(records)
    if latest is not None and latest > 0:
        return latest

    annual = resolve_annual_dividend_per_share(records, document, stock)
    if annual is None or annual <= 0:
        return None

    freq = payments_per_year(
        records,
        stored_frequency=document.payment_frequency if document else None,
    )
    return round(annual / freq, 4)
