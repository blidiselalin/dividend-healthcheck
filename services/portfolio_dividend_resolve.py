"""
Resolve dividend history for portfolio holdings across exposed data sources.

Priority for payment history:
  market library → Postgres history tables → Yahoo Finance series
Payment dates: library → local CSV → Nasdaq → Yahoo calendar → median lag
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from data_ingestion.models import DividendRecord, StockDocument
from services.dividend_payment_dates import (
    _build_payment_date_lookup,
    enrich_document_payment_dates,
)
from utils.dividend_amounts import resolve_annual_dividend_per_share

if TYPE_CHECKING:
    from models.stock import StockData

logger = logging.getLogger(__name__)

EXPOSED_SOURCES: tuple[str, ...] = (
    "market library",
    "Postgres history",
    "local CSV downloads",
    "Nasdaq",
    "Yahoo Finance",
)

_PAYMENT_SOURCE_LABELS: dict[str, str] = {
    "document": "market library",
    "local_csv": "local CSV downloads",
    "nasdaq_api": "Nasdaq",
    "yahoo": "Yahoo Finance",
    "yahoo_calendar": "Yahoo Finance",
    "yahoo_info": "Yahoo Finance",
}


@dataclass(frozen=True)
class PortfolioDividendStatus:
    """Where dividend data was found (or not) for one portfolio symbol."""

    symbol: str
    history_count: int
    sources_checked: tuple[str, ...]
    sources_found: tuple[str, ...]
    payment_date_sources: tuple[str, ...]
    uses_metadata_fallback: bool = False

    @property
    def has_dividend_history(self) -> bool:
        return self.history_count > 0

    @property
    def missing_message(self) -> str | None:
        if self.has_dividend_history:
            return None
        if self.uses_metadata_fallback:
            return (
                "No dividend payment history in exposed sources "
                f"({self._checked_label()}); using annual dividend estimate from stock metadata."
            )
        return "No dividend history found in exposed sources " f"({self._checked_label()})."

    @property
    def sources_summary(self) -> str | None:
        if not self.sources_found:
            return None
        return ", ".join(self.sources_found)

    def _checked_label(self) -> str:
        return ", ".join(self.sources_checked)


def _label_payment_sources(raw: set[str]) -> tuple[str, ...]:
    labels: list[str] = []
    seen: set[str] = set()
    for key in sorted(raw):
        label = _PAYMENT_SOURCE_LABELS.get(key, key.replace("_", " "))
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return tuple(labels)


def _records_from_yfinance(symbol: str) -> list[DividendRecord]:
    from utils.yfinance_history import fetch_dividend_series

    series = fetch_dividend_series(symbol)
    if series is None or series.empty:
        return []

    records: list[DividendRecord] = []
    for ts, amount in series.items():
        try:
            ex = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
            value = float(amount)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        records.append(DividendRecord(ex_date=ex, payment_date=None, amount=value))
    return records


def _merge_dividend_records(
    primary: list[DividendRecord],
    supplemental: list[DividendRecord],
) -> list[DividendRecord]:
    by_ex: dict[date, DividendRecord] = {record.ex_date: record for record in primary}
    for record in supplemental:
        by_ex.setdefault(record.ex_date, record)
    return sorted(by_ex.values(), key=lambda item: item.ex_date)


def _attach_postgres_history(document: StockDocument | None) -> StockDocument | None:
    if document is None:
        return document
    try:
        from db.connection import use_cloud_sql

        if not use_cloud_sql():
            return document
        from db.postgres_market_history_store import PostgresMarketHistoryStore

        return PostgresMarketHistoryStore().attach_history_to_document(document)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Postgres dividend history attach failed: %s", exc)
        return document


def resolve_dividend_document(
    symbol: str,
    document: StockDocument | None,
    *,
    stock: StockData | None = None,
    fetch_remote: bool = False,
) -> tuple[StockDocument | None, PortfolioDividendStatus]:
    """
    Merge dividend history from library + Yahoo and enrich payment dates.

    Does not write back to the market library — returns an in-memory document
    suitable for portfolio calculations and UI.
    """
    sym = symbol.strip().upper()
    sources_checked: list[str] = ["market library", "Postgres history", "Yahoo Finance"]
    sources_found: list[str] = []

    doc = _attach_postgres_history(document)
    before_count = len(document.dividend_history) if document and document.dividend_history else 0
    library_records = list(doc.dividend_history) if doc and doc.dividend_history else []
    if library_records:
        sources_found.append("market library")
    if len(library_records) > before_count:
        sources_found.append("Postgres history")

    yf_records: list[DividendRecord] = []
    if len(library_records) < 4:
        yf_records = _records_from_yfinance(sym)
        if yf_records and "Yahoo Finance" not in sources_found:
            sources_found.append("Yahoo Finance")

    merged = _merge_dividend_records(library_records, yf_records)
    uses_metadata = False
    if not merged:
        annual = resolve_annual_dividend_per_share([], doc, stock)
        uses_metadata = annual is not None and annual > 0
        status = PortfolioDividendStatus(
            symbol=sym,
            history_count=0,
            sources_checked=tuple(sources_checked),
            sources_found=tuple(sources_found),
            payment_date_sources=(),
            uses_metadata_fallback=uses_metadata,
        )
        return doc, status

    if doc is None:
        doc = StockDocument(symbol=sym, name=sym)
    doc.dividend_history = merged

    doc = enrich_document_payment_dates(sym, doc, fetch_nasdaq=fetch_remote)
    payment_lookup = _build_payment_date_lookup(
        sym,
        document_records=list(doc.dividend_history or []) if doc else [],
        fetch_remote=fetch_remote,
    )
    pay_labels = _label_payment_sources(payment_lookup.sources)
    for label in pay_labels:
        if label not in sources_found and label in EXPOSED_SOURCES:
            sources_found.append(label)

    status = PortfolioDividendStatus(
        symbol=sym,
        history_count=len(doc.dividend_history or []) if doc else 0,
        sources_checked=tuple(sources_checked),
        sources_found=tuple(sources_found),
        payment_date_sources=pay_labels,
        uses_metadata_fallback=False,
    )
    return doc, status


def load_resolved_portfolio_documents(
    symbols: list[str],
    documents: dict[str, StockDocument | None] | None = None,
    *,
    stock_data: dict[str, StockData | None] | None = None,
    fetch_remote: bool = False,
) -> tuple[dict[str, StockDocument | None], dict[str, PortfolioDividendStatus]]:
    """Load and resolve dividend documents for all portfolio symbols."""
    from services.shared_market_db import load_documents

    raw = dict(documents) if documents is not None else load_documents(symbols)
    stock_data = stock_data or {}
    resolved: dict[str, StockDocument | None] = {}
    statuses: dict[str, PortfolioDividendStatus] = {}

    for symbol in symbols:
        sym = symbol.strip().upper()
        doc, status = resolve_dividend_document(
            sym,
            raw.get(sym) or raw.get(symbol),
            stock=stock_data.get(sym) or stock_data.get(symbol),
            fetch_remote=fetch_remote,
        )
        resolved[sym] = doc
        statuses[sym] = status

    return resolved, statuses
