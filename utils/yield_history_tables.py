"""
Yearly dividend / yield tables for charts and data-exposure panels.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def year_column_label(year: int, *, today: Optional[date] = None) -> str:
    """Format a calendar year for tables/charts; current year is marked estimated."""
    today = today or date.today()
    if year == today.year:
        return f"{year} (est.)"
    return str(year)


def _payment_counts_by_year(records: List[Any]) -> Dict[int, int]:
    counts: Dict[int, int] = defaultdict(int)
    for record in records:
        ex = getattr(record, "ex_date", None)
        if ex is not None:
            counts[int(ex.year)] += 1
    return dict(counts)


def estimate_annual_dividend_for_year(
    year: int,
    ytd_total: float,
    payment_count: int,
    *,
    document: Any = None,
    all_records: Optional[List[Any]] = None,
    today: Optional[date] = None,
) -> Tuple[float, str, Optional[float]]:
    """
    Return (display_dps, status, ytd_paid) for a calendar year.

    Complete years use the summed payments. The current partial year uses a
    projected full-year DPS so it can be compared fairly with prior years.
    """
    today = today or date.today()
    ytd_paid = round(float(ytd_total), 4) if ytd_total else None

    if year != today.year:
        return round(float(ytd_total), 4), "Complete", None

    if document is not None:
        for attr in ("annual_dividend", "dividend_rate"):
            declared = getattr(document, attr, None)
            if declared is not None and float(declared) > 0:
                return (
                    round(float(declared), 4),
                    "Estimated (declared rate)",
                    ytd_paid,
                )

    records = all_records or []
    if records and payment_count > 0:
        prior_counts = [
            count
            for pay_year, count in _payment_counts_by_year(records).items()
            if pay_year < year and pay_year >= year - 5
        ]
        if prior_counts:
            typical = max(round(sum(prior_counts) / len(prior_counts)), payment_count)
            if typical > payment_count and ytd_total > 0:
                return (
                    round(ytd_total * typical / payment_count, 4),
                    f"Estimated ({payment_count}/{typical} payments)",
                    ytd_paid,
                )

        prior_year_total = sum(
            float(getattr(record, "amount", 0) or 0)
            for record in records
            if getattr(record, "ex_date", None) and record.ex_date.year == year - 1
        )
        if prior_year_total > 0:
            return (
                round(prior_year_total, 4),
                "Estimated (prior year)",
                ytd_paid,
            )

    if ytd_total > 0:
        month = max(today.month, 1)
        return (
            round(ytd_total * 12 / month, 4),
            "Estimated (YTD scaled)",
            ytd_paid,
        )

    return round(float(ytd_total), 4), "Estimated", ytd_paid


def yearly_dividend_per_share_table(document: Any, *, since_year: Optional[int] = None) -> pd.DataFrame:
    """Annual dividend per share from library ``dividend_history``."""
    records = getattr(document, "dividend_history", None) or []
    if not records:
        return pd.DataFrame()

    totals: Dict[int, float] = defaultdict(float)
    counts: Dict[int, int] = defaultdict(int)
    for record in records:
        ex = getattr(record, "ex_date", None)
        amount = getattr(record, "amount", None)
        if ex is None or amount is None:
            continue
        if since_year is not None and ex.year < since_year:
            continue
        year = int(ex.year)
        totals[year] += float(amount)
        counts[year] += 1

    if not totals:
        return pd.DataFrame()

    today = date.today()
    rows = []
    for year in sorted(totals):
        display_dps, status, ytd_paid = estimate_annual_dividend_for_year(
            year,
            totals[year],
            counts[year],
            document=document,
            all_records=records,
            today=today,
        )
        row: Dict[str, Any] = {
            "Year": year_column_label(year, today=today),
            "Dividend / share $": display_dps,
            "Status": status,
        }
        if ytd_paid is not None:
            row["YTD paid $"] = ytd_paid
        rows.append(row)

    return pd.DataFrame(rows)


def yearly_yield_exposure_table(channel_data: Any, *, today: Optional[date] = None) -> pd.DataFrame:
    """
    Year-by-year trailing yield, price, and dividend from yield-channel series.

    Used when the 10-year chart is available or as a compact history export.
    """
    today = today or date.today()
    dates = getattr(channel_data, "dates", None) or []
    yields = getattr(channel_data, "yields", None) or []
    prices = getattr(channel_data, "prices", None) or []
    dividends = getattr(channel_data, "annual_dividends", None) or []
    if not dates or not yields:
        return pd.DataFrame()

    buckets: Dict[int, Dict[str, List[float]]] = defaultdict(
        lambda: {"yields": [], "prices": [], "divs": []}
    )
    for index, raw_date in enumerate(dates):
        if isinstance(raw_date, date):
            year = raw_date.year
        else:
            year = pd.Timestamp(raw_date).year
        if index < len(yields):
            buckets[year]["yields"].append(float(yields[index]))
        if index < len(prices):
            buckets[year]["prices"].append(float(prices[index]))
        if index < len(dividends):
            buckets[year]["divs"].append(float(dividends[index]))

    rows: List[Dict[str, Any]] = []
    for year in sorted(buckets):
        info = buckets[year]
        avg_yield = sum(info["yields"]) / len(info["yields"]) if info["yields"] else None
        end_price = info["prices"][-1] if info["prices"] else None
        trailing_div = info["divs"][-1] if info["divs"] else None
        is_current = year == today.year
        rows.append(
            {
                "Year": year_column_label(year, today=today),
                "Avg yield %": round(avg_yield, 2) if avg_yield is not None else None,
                "Year-end price $": round(end_price, 2) if end_price is not None else None,
                "Trailing div $": round(trailing_div, 2) if trailing_div is not None else None,
                "Status": "Estimated (partial year)" if is_current else "Complete",
            }
        )
    return pd.DataFrame(rows)
