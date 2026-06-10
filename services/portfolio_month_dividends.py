"""
Current-month dividend cash already paid (gross from receipts, net after tax when synced).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional, Tuple

from data_ingestion.dividend_income_store import MONTH_LABELS, DividendIncomeStore
from data_ingestion.dividend_receipt_store import DividendReceiptStore
from data_ingestion.portfolio_store import PortfolioStore
from services.portfolio_dividend_calendar import build_portfolio_dividend_calendar

if TYPE_CHECKING:
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_details_service import PortfolioDetailRow


@dataclass(frozen=True)
class CurrentMonthPaidDividends:
    """Dividend cash received in the current calendar month (paid through today)."""

    month_label: str
    through_date: date
    gross_usd: float
    net_usd: Optional[float]
    payer_count: int

    @property
    def through_label(self) -> str:
        return f"through {self.through_date.day} {MONTH_LABELS[self.through_date.month - 1]}"


def net_received_through(gross_usd: float, *, year: int) -> Optional[float]:
    """Estimate net cash received after withholding from gross paid through today."""
    if gross_usd <= 0:
        return None
    from data_ingestion.dividend_income_store import dividend_tax_rate

    rate = dividend_tax_rate(year)
    return round(gross_usd * (1.0 - rate), 2)


def month_label_for(day: date) -> str:
    return f"{MONTH_LABELS[day.month - 1]} {day.year}"


def gross_paid_in_calendar_month(
    year: int,
    month: int,
    *,
    through: Optional[date] = None,
    store: Optional[DividendReceiptStore] = None,
) -> Tuple[float, int]:
    """Sum gross receipts with pay_date in the month, capped at `through` (default today)."""
    through = through or date.today()
    if (year, month) > (through.year, through.month):
        return 0.0, 0

    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)
    cutoff = month_end if (year, month) < (through.year, through.month) else through
    start = date(year, month, 1).isoformat()
    end = cutoff.isoformat()

    receipt_store = store or DividendReceiptStore()
    with receipt_store._connect() as connection:
        if connection.is_postgres:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(gross_usd), 0) AS gross,
                       COUNT(*) AS receipt_count
                FROM dividend_receipts
                WHERE user_id = ?
                  AND pay_date >= ?
                  AND pay_date <= ?
                """,
                (connection.user_id, start, end),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(gross_usd), 0) AS gross,
                       COUNT(*) AS receipt_count
                FROM dividend_receipts
                WHERE pay_date >= ?
                  AND pay_date <= ?
                """,
                (start, end),
            ).fetchone()

    if not row:
        return 0.0, 0
    return round(float(row["gross"]), 2), int(row["receipt_count"])


def net_paid_in_calendar_month(
    year: int,
    month: int,
    *,
    store: Optional[DividendIncomeStore] = None,
) -> Optional[float]:
    income_store = store or DividendIncomeStore()
    for item in income_store.list_dividends():
        if item.year == year and item.month == month:
            return round(item.net_usd, 2)
    return None


def current_month_paid_dividends(
    *,
    rows: Optional[list["PortfolioDetailRow"]] = None,
    preload: Optional["PortfolioAnalysisPreload"] = None,
    reference_date: Optional[date] = None,
) -> Optional[CurrentMonthPaidDividends]:
    """
    Paid dividend cash for the current month through `reference_date` (default today).

    Uses synced receipts first; falls back to the dividend calendar received total.
    Always returns a snapshot when the portfolio has rows (including $0.00).
    """
    today = reference_date or date.today()
    if not rows:
        if not PortfolioStore().list_holdings():
            return None
        rows = []

    gross, payer_count = gross_paid_in_calendar_month(today.year, today.month, through=today)

    if gross == 0.0 and payer_count == 0 and rows and preload:
        holdings = PortfolioStore().list_holdings()
        if holdings:
            row_dates = {
                row.ticker: (row.ex_dividend_date, row.dividend_pay_date) for row in rows
            }
            calendar = build_portfolio_dividend_calendar(
                holdings,
                vector_docs=preload.vector_docs,
                stock_data=preload.stock_data,
                row_dates=row_dates,
                reference_date=today,
            )
            current = calendar.current_month
            gross = current.received_cash
            payer_count = current.received_payer_count

    net = net_received_through(gross, year=today.year)

    return CurrentMonthPaidDividends(
        month_label=month_label_for(today),
        through_date=today,
        gross_usd=gross,
        net_usd=net,
        payer_count=payer_count,
    )
