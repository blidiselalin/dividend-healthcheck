"""
Canonical dividend document resolution, month cash totals, and data-gap warnings.

All portfolio dividend cash views should use this module instead of ad hoc
``load_documents`` / partial preload paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from data_ingestion.portfolio_store import PortfolioHolding

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument
    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from services.portfolio_details_service import PortfolioDetailRow
    from services.portfolio_dividend_resolve import PortfolioDividendStatus


@dataclass(frozen=True)
class DividendDataWarning:
    """A holding whose dividend cash cannot be fully computed from library data."""

    symbol: str
    level: str
    message: str


@dataclass(frozen=True)
class MonthDividendCash:
    """Gross/net dividend cash for one calendar month through ``through_date``."""

    gross_usd: float
    net_usd: float | None
    payer_count: int
    source: str


def _symbol_keys(symbol: str) -> set[str]:
    sym = symbol.strip().upper()
    return {sym, symbol.strip()}


def resolve_dividend_documents(
    holdings: list[PortfolioHolding],
    preload: PortfolioAnalysisPreload | None = None,
    *,
    fetch_remote: bool = False,
) -> tuple[dict[str, StockDocument], dict[str, PortfolioDividendStatus]]:
    """
    Resolved dividend documents for all ``holdings``.

    Always re-resolves every open holding through the library + payment-date
    pipeline so partial session caches cannot leave symbols with empty history.
    """
    from services.portfolio_dividend_resolve import load_resolved_portfolio_documents

    seed_docs: dict[str, StockDocument | None] = {}
    statuses: dict[str, PortfolioDividendStatus] = {}

    if preload and getattr(preload, "vector_docs", None):
        for symbol, document in preload.vector_docs.items():
            sym = symbol.strip().upper()
            seed_docs[sym] = document
            if document is not None:
                seed_docs[symbol] = document

    if preload and getattr(preload, "dividend_statuses", None):
        for symbol, status in preload.dividend_statuses.items():
            statuses[symbol.strip().upper()] = status

    if not holdings:
        docs = {sym: doc for sym, doc in seed_docs.items() if doc is not None}
        return docs, statuses

    all_symbols = [holding.symbol for holding in holdings]
    resolved, new_statuses = load_resolved_portfolio_documents(
        all_symbols,
        documents=seed_docs or None,
        fetch_remote=fetch_remote,
    )
    docs = {
        symbol.strip().upper(): document
        for symbol, document in resolved.items()
        if document is not None
    }
    statuses.update(new_statuses)
    return docs, statuses


def resolve_month_dividend_cash(
    *,
    year: int,
    month: int,
    through: date,
    holdings: list[PortfolioHolding],
    vector_docs: dict[str, StockDocument],
) -> MonthDividendCash:
    """
    Gross/net cash for one month through ``through``.

    Precedence: synced ``dividend_receipts`` when present, else live compute from
    resolved library history, else zero.
    """
    from services.portfolio_month_dividends import (
        _resolve_month_gross_and_net,
        compute_month_received_from_holdings,
        gross_paid_in_calendar_month,
    )

    db_gross, db_count = gross_paid_in_calendar_month(year, month, through=through)
    computed_gross = 0.0
    computed_count = 0
    if holdings and vector_docs:
        computed_gross, computed_count = compute_month_received_from_holdings(
            holdings,
            vector_docs,
            reference_date=through,
        )

    gross, payer_count, net = _resolve_month_gross_and_net(
        year=year,
        month=month,
        through=through,
        db_gross=db_gross,
        db_count=db_count,
        computed_gross=computed_gross,
        computed_count=computed_count,
    )

    if db_count > 0:
        source = "receipts"
    elif computed_count > 0:
        source = "computed"
    elif gross > 0:
        source = "receipts"
    else:
        source = "none"

    return MonthDividendCash(
        gross_usd=gross,
        net_usd=net,
        payer_count=payer_count,
        source=source,
    )


def build_merged_dividend_income_records(
    *,
    store: Any | None = None,
    receipt_store: Any | None = None,
    holdings: list[PortfolioHolding] | None = None,
    preload: PortfolioAnalysisPreload | None = None,
) -> list[Any]:
    """
    Monthly dividend income for display: stored ``net_dividends`` merged with
    broker-imported receipt aggregates.

    IBKR import populates ``dividend_receipts`` and ``net_dividends`` directly —
    those rows are authoritative. Market-library recompute only fills recent months
    that are still missing after import/sync.
    """
    import calendar as cal

    from data_ingestion.dividend_income_store import (
        MONTH_LABELS,
        MonthlyNetDividend,
        dividend_tax_rate,
    )
    from services.portfolio_context import create_portfolio_context

    ctx = create_portfolio_context()
    income_store = store or ctx.dividends
    receipts = receipt_store or ctx.receipts
    holdings = holdings if holdings is not None else ctx.portfolio.list_open_holdings()
    by_key: dict[str, MonthlyNetDividend] = {
        item.period_key: item for item in income_store.list_dividends()
    }

    def _upsert_month(year: int, month: int, gross: float) -> None:
        if gross <= 0:
            return
        key = f"{year:04d}-{month:02d}"
        rate = dividend_tax_rate(year)
        net = round(gross * (1.0 - rate), 2)
        existing = by_key.get(key)
        if existing is not None and existing.gross_usd >= gross - 0.01:
            return
        by_key[key] = MonthlyNetDividend(
            period=date(year, month, 1),
            year=year,
            month=month,
            month_label=MONTH_LABELS[month - 1],
            net_usd=net,
            tax_rate_pct=rate * 100,
            gross_usd=round(gross, 2),
            tax_withheld_usd=round(gross - net, 2),
        )

    for (year, month), gross in receipts.monthly_gross_totals().items():
        _upsert_month(year, month, gross)

    if holdings:
        docs, _ = resolve_dividend_documents(holdings, preload)
        today = date.today()
        recent_months = [(today.year, today.month)]
        if today.month == 1:
            recent_months.append((today.year - 1, 12))
        else:
            recent_months.append((today.year, today.month - 1))

        for year, month in recent_months:
            key = f"{year:04d}-{month:02d}"
            existing = by_key.get(key)
            if existing is not None and existing.gross_usd > 0:
                continue
            last_day = cal.monthrange(year, month)[1]
            through = (
                today if (year, month) == (today.year, today.month) else date(year, month, last_day)
            )
            cash = resolve_month_dividend_cash(
                year=year,
                month=month,
                through=through,
                holdings=holdings,
                vector_docs=docs,
            )
            _upsert_month(year, month, cash.gross_usd)

    return sorted(by_key.values(), key=lambda item: (item.year, item.month))


def ensure_dividend_cash_materialized(*, force_sync: bool = False) -> bool:
    """
    Populate ``dividend_receipts`` / ``net_dividends`` when recent months are empty.

    Returns True when a background sync was scheduled or ran inline.
    Skips when IBKR import or a prior sync already stored receipts or monthly totals.
    """
    from services.portfolio_context import create_portfolio_context
    from services.portfolio_month_dividends import gross_paid_in_calendar_month

    ctx = create_portfolio_context()
    holdings = ctx.portfolio.list_open_holdings()
    if not holdings:
        return False

    today = date.today()
    _, receipt_count = gross_paid_in_calendar_month(
        today.year,
        today.month,
        through=today,
        store=ctx.receipts,
    )
    has_receipt_history = bool(ctx.receipts.monthly_gross_totals())
    has_stored = any(item.gross_usd > 0 for item in ctx.dividends.list_dividends())

    if not force_sync and (receipt_count > 0 or has_receipt_history or has_stored):
        return False

    try:
        from services.deferred_startup import schedule_forced_dividend_sync

        schedule_forced_dividend_sync()
        return True
    except ImportError:
        from services.portfolio_dividend_sync_service import sync_received_dividends

        sync_received_dividends(fetch_remote=force_sync)
        return True


def collect_dividend_data_warnings(
    holdings: list[PortfolioHolding],
    vector_docs: dict[str, StockDocument],
    statuses: dict[str, PortfolioDividendStatus],
    *,
    rows: list[PortfolioDetailRow] | None = None,
) -> list[DividendDataWarning]:
    """Symbols missing payment history or relying on metadata-only estimates."""
    warnings: list[DividendDataWarning] = []
    row_by_ticker = {row.ticker.strip().upper(): row for row in (rows or [])}

    for holding in holdings:
        sym = holding.symbol.strip().upper()
        status = statuses.get(sym) or statuses.get(holding.symbol)
        document = vector_docs.get(sym) or vector_docs.get(holding.symbol)
        row = row_by_ticker.get(sym)

        if status and getattr(status, "uses_metadata_fallback", False):
            message = status.missing_message or (
                f"{sym}: no payment history in library — using annual dividend estimate only."
            )
            warnings.append(DividendDataWarning(symbol=sym, level="metadata_only", message=message))
            continue

        history = document.dividend_history if document else None
        history_count = len(history) if history else 0
        if history_count == 0:
            row_status = getattr(row, "dividend_data_status", None) if row else None
            if row_status and "annual dividend estimate" in row_status.lower():
                warnings.append(
                    DividendDataWarning(
                        symbol=sym,
                        level="metadata_only",
                        message=row_status,
                    )
                )
            elif (row and (row.annual_income or 0) > 0) or (
                status and getattr(status, "uses_metadata_fallback", False)
            ):
                warnings.append(
                    DividendDataWarning(
                        symbol=sym,
                        level="metadata_only",
                        message=(
                            f"{sym}: forward income uses metadata but no dated payment "
                            "history is stored — monthly cash may show $0."
                        ),
                    )
                )
            else:
                message = (
                    status.missing_message
                    if status and status.missing_message
                    else (
                        f"{sym}: no dividend payment history in market library, Postgres, "
                        "Nasdaq, or Yahoo — sync or import may be required."
                    )
                )
                warnings.append(
                    DividendDataWarning(symbol=sym, level="missing_history", message=message)
                )
            continue

        if status and status.missing_message and not status.has_dividend_history:
            warnings.append(
                DividendDataWarning(
                    symbol=sym,
                    level="missing_history",
                    message=status.missing_message,
                )
            )

    return warnings


def render_dividend_data_warnings_streamlit(warnings: list[DividendDataWarning]) -> None:
    """Show grouped dividend data gaps in Streamlit (no-op when empty)."""
    if not warnings:
        return
    try:
        import streamlit as st
    except ImportError:
        return

    missing = [item for item in warnings if item.level == "missing_history"]
    metadata = [item for item in warnings if item.level == "metadata_only"]

    if missing:
        tickers = ", ".join(item.symbol for item in missing[:10])
        suffix = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
        st.warning(
            f"**Missing dividend history:** {tickers}{suffix}. "
            "Upcoming ex-dates and monthly **estimates** may show **$0** until the market "
            "library is populated or you run **Sync dividends**. "
            "**Imported broker payments** are shown separately from receipts.",
            icon="⚠️",
        )
        with st.expander("Details — symbols without payment history"):
            for item in missing:
                st.caption(f"**{item.symbol}** — {item.message}")

    if metadata:
        tickers = ", ".join(item.symbol for item in metadata[:10])
        suffix = f" (+{len(metadata) - 10} more)" if len(metadata) > 10 else ""
        st.info(
            f"**Estimate only:** {tickers}{suffix} — annual income uses metadata; "
            "dated payment history is not in the database.",
            icon="ℹ️",
        )
