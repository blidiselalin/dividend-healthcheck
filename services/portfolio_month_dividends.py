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
from data_ingestion.portfolio_store import PortfolioHolding
from services.portfolio_context import create_portfolio_context
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
    net_is_estimate: bool = True
    scope: str = "open_holdings"

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
    *,
    fetch_remote: bool = False,
) -> dict[str, StockDocument]:
    from services.portfolio_dividend_cash import resolve_dividend_documents

    docs, _statuses = resolve_dividend_documents(
        holdings,
        preload,
        fetch_remote=fetch_remote,
    )
    return docs


def compute_month_received_from_holdings(
    holdings: list[PortfolioHolding],
    vector_docs: dict[str, StockDocument],
    *,
    reference_date: date,
) -> tuple[float, int]:
    """
    Gross cash received this month through `reference_date`.

    Per holding: imported ``dividend_receipts`` for the month win; otherwise library
    history with journal share counts.
    """
    from services.portfolio_holding_detail_service import PortfolioHoldingDetailService

    detail = PortfolioHoldingDetailService()
    total = 0.0
    count = 0
    seen: set[tuple[str, str, float]] = set()

    for holding in holdings:
        document = vector_docs.get(holding.symbol.upper()) or vector_docs.get(holding.symbol)
        stored = detail.stored_dividend_history(holding.symbol)
        month_stored = [
            row
            for row in stored
            if row.pay_date.year == reference_date.year
            and row.pay_date.month == reference_date.month
            and row.pay_date <= reference_date
            and (
                holding.dividend_tracking_since is None
                or row.pay_date >= holding.dividend_tracking_since
            )
        ]
        if month_stored:
            rows = month_stored
        elif document and document.dividend_history:
            rows = detail.dividend_history(
                holding.symbol,
                document,
                current_shares=holding.shares,
                tracking_since=holding.dividend_tracking_since,
                prefer_stored=False,
            )
            rows = [
                row
                for row in rows
                if row.pay_date.year == reference_date.year
                and row.pay_date.month == reference_date.month
                and row.pay_date <= reference_date
            ]
        else:
            continue

        for row in rows:
            key = (
                holding.symbol.upper(),
                row.ex_date.isoformat(),
                round(row.per_share_usd, 6),
            )
            if key in seen:
                continue
            seen.add(key)
            total += row.cash_usd
            count += 1

    return round(total, 2), count


def _receipt_month_sums(
    year: int,
    month: int,
    *,
    through: date | None = None,
    store: DividendReceiptStore | None = None,
    symbols: set[str] | None = None,
) -> tuple[float, int, float]:
    """Gross, row count, and stored net for receipts with pay_date in the month."""
    through = through or date.today()
    if (year, month) > (through.year, through.month):
        return 0.0, 0, 0.0

    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)
    cutoff = month_end if (year, month) < (through.year, through.month) else through
    start = date(year, month, 1).isoformat()
    end = cutoff.isoformat()

    symbol_filter = ""
    symbol_params: tuple[str, ...] = ()
    if symbols:
        normalized = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
        if normalized:
            placeholders = ",".join("?" * len(normalized))
            symbol_filter = f" AND symbol IN ({placeholders})"
            symbol_params = tuple(normalized)

    receipt_store = store or DividendReceiptStore()
    with receipt_store._connect() as connection:
        if connection.is_postgres:
            row = connection.execute(
                f"""
                SELECT COALESCE(SUM(gross_usd), 0) AS gross,
                       COUNT(*) AS receipt_count,
                       COALESCE(SUM(COALESCE(net_usd, gross_usd - withholding_usd)), 0) AS net
                FROM dividend_receipts
                WHERE user_id = ?
                  AND pay_date >= ?
                  AND pay_date <= ?{symbol_filter}
                """,
                (connection.user_id, start, end, *symbol_params),
            ).fetchone()
        else:
            row = connection.execute(
                f"""
                SELECT COALESCE(SUM(gross_usd), 0) AS gross,
                       COUNT(*) AS receipt_count,
                       COALESCE(SUM(COALESCE(net_usd, gross_usd - withholding_usd)), 0) AS net
                FROM dividend_receipts
                WHERE pay_date >= ?
                  AND pay_date <= ?{symbol_filter}
                """,
                (start, end, *symbol_params),
            ).fetchone()

    if not row:
        return 0.0, 0, 0.0
    return (
        round(float(row["gross"]), 2),
        int(row["receipt_count"]),
        round(float(row["net"]), 2),
    )


def gross_paid_in_calendar_month(
    year: int,
    month: int,
    *,
    through: date | None = None,
    store: DividendReceiptStore | None = None,
    symbols: set[str] | None = None,
) -> tuple[float, int]:
    """Sum gross receipts with pay_date in the month, capped at `through` (default today)."""
    gross, count, _net = _receipt_month_sums(
        year,
        month,
        through=through,
        store=store,
        symbols=symbols,
    )
    return gross, count


def net_paid_from_receipts(
    year: int,
    month: int,
    *,
    through: date | None = None,
    store: DividendReceiptStore | None = None,
    symbols: set[str] | None = None,
) -> float | None:
    """Stored net for the month, or None when the month has no receipt rows."""
    _gross, count, net = _receipt_month_sums(
        year,
        month,
        through=through,
        store=store,
        symbols=symbols,
    )
    if count <= 0:
        return None
    return net


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


def gross_paid_in_synced_month(
    year: int,
    month: int,
    *,
    store: DividendIncomeStore | None = None,
) -> float | None:
    """Gross USD stored alongside synced monthly net totals (when available)."""
    income_store = store or DividendIncomeStore()
    for item in income_store.list_dividends():
        if item.year == year and item.month == month:
            return round(item.gross_usd, 2)
    return None


def _resolve_month_gross_and_net(
    *,
    year: int,
    month: int,
    through: date,
    db_gross: float,
    db_count: int,
    computed_gross: float,
    computed_count: int,
    receipt_net: float | None = None,
) -> tuple[float, int, float | None, bool]:
    """
    Choose gross, payer count, net, and whether net is an estimate.

    Posted receipts are the received total. A library recompute is used only
    when the month has no receipt rows, and that net is always an estimate.
    ``month`` and ``through`` identify the period for callers; the sums are
    already bounded before this function runs.
    """
    del month, through
    if db_count > 0:
        gross, payer_count = db_gross, db_count
        if receipt_net is not None:
            return gross, payer_count, round(receipt_net, 2), False
        if gross > 0:
            return gross, payer_count, net_received_through(gross, year=year), True
        return gross, payer_count, None, True

    if computed_count > 0 and computed_gross > 0:
        gross, payer_count = computed_gross, computed_count
    else:
        gross, payer_count = db_gross, db_count

    if gross > 0:
        return gross, payer_count, net_received_through(gross, year=year), True
    return gross, payer_count, None, True


def current_month_paid_dividends(
    *,
    rows: list[PortfolioDetailRow] | None = None,
    preload: PortfolioAnalysisPreload | None = None,
    reference_date: date | None = None,
) -> CurrentMonthPaidDividends | None:
    """
    Paid dividend cash for the current month through `reference_date` (default today).

    Uses synced receipts when available, otherwise live compute from resolved library
    history (Yahoo-aligned pay dates). Falls back to the dividend calendar when docs
    are unavailable.
    """
    from services.portfolio_dividend_cash import (
        collect_dividend_data_warnings,
        render_dividend_data_warnings_streamlit,
        resolve_dividend_documents,
        resolve_month_dividend_cash,
    )

    today = reference_date or date.today()
    ctx = create_portfolio_context()
    holdings = ctx.portfolio.list_open_holdings()

    if rows is None:
        if not holdings:
            return None
        rows = []

    vector_docs, dividend_statuses = resolve_dividend_documents(holdings, preload)

    if holdings:
        warnings = collect_dividend_data_warnings(
            holdings,
            vector_docs,
            dividend_statuses,
            rows=rows,
        )
        try:
            import streamlit as st

            if warnings:
                shown = st.session_state.get("_dividend_data_warnings_fp")
                fp = st.session_state.get("_portfolio_db_fingerprint", "")
                if shown != fp:
                    render_dividend_data_warnings_streamlit(warnings)
                    st.session_state["_dividend_data_warnings_fp"] = fp
        except ImportError:
            pass

    if holdings and vector_docs:
        month_cash = resolve_month_dividend_cash(
            year=today.year,
            month=today.month,
            through=today,
            holdings=holdings,
            vector_docs=vector_docs,
        )
        gross, payer_count, net = (
            month_cash.gross_usd,
            month_cash.payer_count,
            month_cash.net_usd,
        )
        net_is_estimate = month_cash.net_is_estimate
        if gross <= 0 and rows and preload:
            row_dates = {row.ticker: (row.ex_dividend_date, row.dividend_pay_date) for row in rows}
            calendar = build_portfolio_dividend_calendar(
                holdings,
                vector_docs=vector_docs,
                stock_data=preload.stock_data if preload else {},
                row_dates=row_dates,
                reference_date=today,
            )
            fallback_gross = calendar.current_month.received_cash
            if fallback_gross > 0:
                gross = fallback_gross
                payer_count = calendar.current_month.received_payer_count
                net = net_received_through(gross, year=today.year)
                net_is_estimate = True
    elif rows and preload and holdings:
        row_dates = {row.ticker: (row.ex_dividend_date, row.dividend_pay_date) for row in rows}
        calendar = build_portfolio_dividend_calendar(
            holdings,
            vector_docs=vector_docs,
            stock_data=preload.stock_data,
            row_dates=row_dates,
            reference_date=today,
        )
        current = calendar.current_month
        gross = current.received_cash
        payer_count = current.received_payer_count
        net = net_received_through(gross, year=today.year)
        net_is_estimate = True
    else:
        open_symbols = {holding.symbol.strip().upper() for holding in holdings}
        db_gross, db_count = gross_paid_in_calendar_month(
            today.year,
            today.month,
            through=today,
            symbols=open_symbols or None,
        )
        receipt_net = net_paid_from_receipts(
            today.year,
            today.month,
            through=today,
            symbols=open_symbols or None,
        )
        gross, payer_count, net, net_is_estimate = _resolve_month_gross_and_net(
            year=today.year,
            month=today.month,
            through=today,
            db_gross=db_gross,
            db_count=db_count,
            computed_gross=0.0,
            computed_count=0,
            receipt_net=receipt_net if db_count > 0 else None,
        )

    return CurrentMonthPaidDividends(
        month_label=month_label_for(today),
        through_date=today,
        gross_usd=gross,
        net_usd=net,
        payer_count=payer_count,
        net_is_estimate=net_is_estimate,
        scope="open_holdings",
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
    except (ImportError, AttributeError):
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
