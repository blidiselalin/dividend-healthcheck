"""
Current-month dividend cash already paid (gross from receipts, net after tax when synced).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from data_ingestion.dividend_income_store import MONTH_LABELS, DividendIncomeStore
from data_ingestion.dividend_receipt_store import DividendReceiptStore
from data_ingestion.portfolio_store import PortfolioHolding, PortfolioStore
from services.portfolio_dividend_calendar import build_portfolio_dividend_calendar

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_details_service import PortfolioDetailRow


@dataclass(frozen=True)
class CurrentMonthPaidDividends:
    """Dividend cash received in the current calendar month (paid through today)."""

    month_label: str
    through_date: date
    gross_usd: float
    net_usd: float | None
    payer_count: int

    @property
    def through_label(self) -> str:
        return f"through {self.through_date.day} {MONTH_LABELS[self.through_date.month - 1]}"


def net_received_through(gross_usd: float, *, year: int) -> float | None:
    """Estimate net cash received after withholding from gross paid through today."""
    if gross_usd <= 0:
        return None
    from data_ingestion.dividend_income_store import dividend_tax_rate

    rate = dividend_tax_rate(year)
    return round(gross_usd * (1.0 - rate), 2)


def month_label_for(day: date) -> str:
    return f"{MONTH_LABELS[day.month - 1]} {day.year}"


def _resolve_vector_docs(
    holdings: list[PortfolioHolding],
    preload: PortfolioAnalysisPreload | None,
) -> dict[str, StockDocument]:
    if preload and preload.vector_docs:
        return preload.vector_docs
    if not holdings:
        return {}
    from services.shared_market_db import load_documents

    symbols = [holding.symbol for holding in holdings]
    return load_documents(symbols)


def compute_month_received_from_holdings(
    holdings: list[PortfolioHolding],
    vector_docs: dict[str, StockDocument],
    *,
    reference_date: date,
) -> tuple[float, int]:
    """
    Gross cash received this month through `reference_date`.

    Matches Yahoo-style portfolio dividends: pay date in month, shares held on ex-date,
    normalized per-payment amounts, purchase journal when available.
    """
    from services.portfolio_holding_detail_service import PortfolioHoldingDetailService

    detail = PortfolioHoldingDetailService()
    total = 0.0
    count = 0
    seen: set[tuple[str, str]] = set()

    for holding in holdings:
        document = vector_docs.get(holding.symbol.upper()) or vector_docs.get(holding.symbol)
        if not document:
            continue
        rows = detail.dividend_history(
            holding.symbol,
            document,
            current_shares=holding.shares,
            tracking_since=holding.dividend_tracking_since,
            prefer_stored=False,
        )
        for row in rows:
            if row.pay_date.year != reference_date.year:
                continue
            if row.pay_date.month != reference_date.month:
                continue
            if row.pay_date > reference_date:
                continue
            key = (holding.symbol.upper(), row.pay_date.isoformat())
            if key in seen:
                continue
            seen.add(key)
            total += row.cash_usd
            count += 1

    return round(total, 2), count


def gross_paid_in_calendar_month(
    year: int,
    month: int,
    *,
    through: date | None = None,
    store: DividendReceiptStore | None = None,
) -> tuple[float, int]:
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
    store: DividendIncomeStore | None = None,
) -> float | None:
    income_store = store or DividendIncomeStore()
    for item in income_store.list_dividends():
        if item.year == year and item.month == month:
            return round(item.net_usd, 2)
    return None


def current_month_paid_dividends(
    *,
    rows: list[PortfolioDetailRow] | None = None,
    preload: PortfolioAnalysisPreload | None = None,
    reference_date: date | None = None,
) -> CurrentMonthPaidDividends | None:
    """
    Paid dividend cash for the current month through `reference_date` (default today).

    Prefers a live recompute from holdings + dividend history (Yahoo-aligned).
    Falls back to the dividend calendar or synced receipts when documents are unavailable.
    Always returns a snapshot when the portfolio has rows (including $0.00).
    """
    today = reference_date or date.today()
    holdings = PortfolioStore().list_holdings()

    if rows is None:
        if not holdings:
            return None
        rows = []

    vector_docs = _resolve_vector_docs(holdings, preload) if holdings else {}
    gross = 0.0
    payer_count = 0

    if holdings and vector_docs:
        gross, payer_count = compute_month_received_from_holdings(
            holdings,
            vector_docs,
            reference_date=today,
        )
    elif rows and preload and holdings:
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
    else:
        gross, payer_count = gross_paid_in_calendar_month(
            today.year, today.month, through=today
        )

    net = net_received_through(gross, year=today.year)

    return CurrentMonthPaidDividends(
        month_label=month_label_for(today),
        through_date=today,
        gross_usd=gross,
        net_usd=net,
        payer_count=payer_count,
    )


def cached_current_month_paid_dividends(
    *,
    rows: list[PortfolioDetailRow] | None = None,
    preload: PortfolioAnalysisPreload | None = None,
    reference_date: date | None = None,
) -> CurrentMonthPaidDividends | None:
    """
    Session-scoped cache for month-to-date dividends.

    Recomputes when the portfolio DB fingerprint or calendar day changes.
    """
    try:
        import streamlit as st
    except Exception:
        return current_month_paid_dividends(
            rows=rows,
            preload=preload,
            reference_date=reference_date,
        )

    today = reference_date or date.today()
    fp = st.session_state.get("_portfolio_db_fingerprint", "")
    cache_day = st.session_state.get("_month_paid_cache_day")
    cache_fp = st.session_state.get("_month_paid_cache_fp")
    if cache_day == today.isoformat() and cache_fp == fp:
        cached = st.session_state.get("_month_paid_cache")
        if cached is not None:
            return cached
    result = current_month_paid_dividends(
        rows=rows,
        preload=preload,
        reference_date=today,
    )
    if result is not None:
        st.session_state["_month_paid_cache"] = result
        st.session_state["_month_paid_cache_day"] = today.isoformat()
        st.session_state["_month_paid_cache_fp"] = fp
    return result
