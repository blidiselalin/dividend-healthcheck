"""
Yearly dividend / yield tables for charts and data-exposure panels.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd


def yearly_dividend_per_share_table(document: Any, *, since_year: Optional[int] = None) -> pd.DataFrame:
    """Annual dividend per share from library ``dividend_history``."""
    records = getattr(document, "dividend_history", None) or []
    if not records:
        return pd.DataFrame()

    totals: Dict[int, float] = defaultdict(float)
    for record in records:
        ex = getattr(record, "ex_date", None)
        amount = getattr(record, "amount", None)
        if ex is None or amount is None:
            continue
        if since_year is not None and ex.year < since_year:
            continue
        totals[int(ex.year)] += float(amount)

    if not totals:
        return pd.DataFrame()

    rows = [{"Year": year, "Dividend / share $": round(value, 4)} for year, value in sorted(totals.items())]
    return pd.DataFrame(rows)


def yearly_yield_exposure_table(channel_data: Any) -> pd.DataFrame:
    """
    Year-by-year trailing yield, price, and dividend from yield-channel series.

    Used when the 10-year chart is available or as a compact history export.
    """
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
        rows.append(
            {
                "Year": year,
                "Avg yield %": round(avg_yield, 2) if avg_yield is not None else None,
                "Year-end price $": round(end_price, 2) if end_price is not None else None,
                "Trailing div $": round(trailing_div, 2) if trailing_div is not None else None,
            }
        )
    return pd.DataFrame(rows)
