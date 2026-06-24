"""
Home positions table — concerns, formatting, and dataframe rows (no Streamlit).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from services.portfolio_details_service import PortfolioDetailRow

_COMPANY_MAX_LEN = 28
_PROFIT_ALERT_PCT = -20.0
_HIGH_YIELD_PCT = 9.0
_LOW_YIELD_PCT = 1.0
_YEAR_DOWN_PCT = -15.0
_HALF_YEAR_DOWN_PCT = -10.0


def _status_badge(row: PortfolioDetailRow) -> str:
    parts: list[str] = []
    if getattr(row, "price_stale", False):
        parts.append("⏳")
    if getattr(row, "history_thin", False):
        parts.append("📉")
    return " ".join(parts) if parts else "✓"


def _day_change_pct(row: PortfolioDetailRow) -> float | None:
    if row.current_price is None or row.previous_close is None or row.previous_close <= 0:
        return None
    return round((row.current_price - row.previous_close) / row.previous_close * 100, 2)


def _pl_progress(profit_pct: float | None) -> float | None:
    """Map P/L % to 0–100 for a progress bar (50 = flat)."""
    if profit_pct is None or (isinstance(profit_pct, float) and pd.isna(profit_pct)):
        return None
    return round(max(0.0, min(100.0, 50.0 + float(profit_pct))), 1)


def position_concerns(
    row: PortfolioDetailRow,
    *,
    risk_hint: str | None = None,
    today: date | None = None,
) -> list[str]:
    """Short labels for issues worth reviewing on the home positions table."""
    today = today or date.today()
    concerns: list[str] = []

    if getattr(row, "price_stale", False):
        concerns.append("Stale price")
    if getattr(row, "history_thin", False):
        concerns.append("Thin history")
    if row.profit_pct is not None and row.profit_pct <= _PROFIT_ALERT_PCT:
        concerns.append("Large loss")
    elif row.profit_pct is not None and row.profit_pct < 0:
        concerns.append("Unrealized loss")
    if row.change_365d_pct is not None and row.change_365d_pct <= _YEAR_DOWN_PCT:
        concerns.append("1Y price down")
    elif row.change_180d_pct is not None and row.change_180d_pct <= _HALF_YEAR_DOWN_PCT:
        concerns.append("6M price down")
    if row.dividend_yield_pct is not None and row.dividend_yield_pct >= _HIGH_YIELD_PCT:
        concerns.append("High yield")
    if row.dividend_yield_pct is not None and 0 < row.dividend_yield_pct < _LOW_YIELD_PCT:
        concerns.append("Low yield")
    if row.growth_years is not None and row.growth_years < 5:
        concerns.append("Short div streak")
    rating = (row.analyst_rating or "").lower()
    if "sell" in rating or "underperform" in rating:
        concerns.append("Analyst negative")
    if row.ex_dividend_date and row.ex_dividend_date >= today:
        concerns.append("Ex-date soon")
    if risk_hint:
        concerns.append(risk_hint)

    # De-dupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in concerns:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique[:6]


def concerns_summary(concerns: list[str]) -> str:
    if not concerns:
        return "—"
    return " · ".join(concerns)


def risk_hints_by_ticker(risk_items: list | None) -> dict[str, str]:
    """First risk reason per symbol from cached attention summary items."""
    if not risk_items:
        return {}
    hints: dict[str, str] = {}
    for item in risk_items:
        symbol = getattr(item, "symbol", None)
        if not symbol or symbol in hints:
            continue
        reasons = getattr(item, "reasons", None) or ()
        if reasons:
            hints[symbol] = str(reasons[0])[:48]
        else:
            hints[symbol] = str(getattr(item, "severity", "risk"))
    return hints


def build_home_positions_dataframe(
    rows: list[PortfolioDetailRow],
    *,
    risk_hints: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Rows for the home All positions table (worst-first order expected by caller)."""
    risk_hints = risk_hints or {}
    records = []
    for row in rows:
        company = row.company or row.ticker
        if len(company) > _COMPANY_MAX_LEN:
            company = company[: _COMPANY_MAX_LEN - 1].rstrip() + "…"
        concerns = position_concerns(row, risk_hint=risk_hints.get(row.ticker))
        day_pct = _day_change_pct(row)
        records.append(
            {
                "Ticker": row.ticker,
                "Company": company,
                "Concerns": concerns_summary(concerns),
                "Status": _status_badge(row),
                "P/L %": row.profit_pct,
                "P/L": _pl_progress(row.profit_pct),
                "Day %": day_pct,
                "1Y %": row.change_365d_pct,
                "Yield %": row.dividend_yield_pct,
                "Weight %": row.weight_pct,
                "Value $": row.current_value,
                "Sector": (row.sector or "—")[:18],
            }
        )
    return pd.DataFrame(records)
