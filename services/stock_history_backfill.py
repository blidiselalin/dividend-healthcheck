"""
Backfill thin price/dividend history in the shared market library.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from config import MIN_YIELD_DIVIDEND_PAYMENTS, MIN_YIELD_PRICE_POINTS
from utils.stock_document_history import history_is_thin, yield_channel_ready

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]


def portfolio_backfill_symbols() -> set[str]:
    """Tickers in the current user's portfolio (holdings + purchase journal)."""
    try:
        from services.portfolio_vector_sync import collect_portfolio_symbols

        return collect_portfolio_symbols()
    except Exception:
        return set()


def sort_backfill_candidates(
    candidates: list[StockDocument],
    *,
    portfolio_symbols: set[str] | None = None,
) -> list[StockDocument]:
    """Portfolio holdings first, then thinnest price/dividend history."""
    from utils.datetime_compat import to_naive_utc

    portfolio = portfolio_symbols if portfolio_symbols is not None else portfolio_backfill_symbols()

    def _key(doc: StockDocument) -> tuple[int, int, int, datetime]:
        sym = (doc.symbol or "").upper()
        return (
            0 if sym in portfolio else 1,
            len(doc.price_history or []),
            len(doc.dividend_history or []),
            to_naive_utc(doc.last_updated) or datetime.min,
        )

    return sorted(candidates, key=_key)


def documents_needing_history_backfill(
    documents: list[StockDocument],
    *,
    portfolio_symbols: set[str] | None = None,
) -> list[StockDocument]:
    """Symbols missing enough price/dividend rows for yield channels."""
    from config import DELISTED_SYMBOLS

    thin: list[StockDocument] = []
    for document in documents:
        symbol = (document.symbol or "").upper()
        if not symbol or symbol in DELISTED_SYMBOLS:
            continue
        if history_is_thin(document):
            thin.append(document)
    return sort_backfill_candidates(thin, portfolio_symbols=portfolio_symbols)


def _resolve_backfill_candidates(
    store: Any,
    *,
    symbols: list[str] | None = None,
    prioritize_portfolio: bool = True,
) -> list[StockDocument]:
    """Documents to enrich, creating missing portfolio rows when needed."""
    portfolio = portfolio_backfill_symbols() if prioritize_portfolio else set()

    if symbols:
        wanted = {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        candidates: list[StockDocument] = []
        for symbol in sorted(wanted):
            document = store.get_by_symbol(symbol)
            if document is None and symbol in portfolio:
                document = _fetch_document_for_backfill(symbol)
            if document is not None and history_is_thin(document):
                candidates.append(document)
        portfolio_filter = portfolio if prioritize_portfolio else None
        return sort_backfill_candidates(candidates, portfolio_symbols=portfolio_filter)

    thin = [
        doc
        for doc in store.get_all_documents()
        if (doc.symbol or "").upper() and history_is_thin(doc)
    ]
    from config import DELISTED_SYMBOLS

    thin = [doc for doc in thin if (doc.symbol or "").upper() not in DELISTED_SYMBOLS]
    portfolio_filter = portfolio if prioritize_portfolio else None
    return sort_backfill_candidates(thin, portfolio_symbols=portfolio_filter)


def _fetch_document_for_backfill(symbol: str) -> StockDocument | None:
    """Fetch a new library document when a portfolio holding is missing from the store."""
    try:
        from data_ingestion.stock_enricher import create_stock_enricher

        return create_stock_enricher(request_delay=0.35).fetch_document(symbol)
    except Exception as exc:
        logger.debug("Could not fetch library document for %s: %s", symbol, exc)
        return None


def backfill_thin_history(
    *,
    limit: int = 40,
    symbols: list[str] | None = None,
    request_delay: float = 0.35,
    progress_callback: ProgressCallback | None = None,
    prioritize_portfolio: bool = True,
) -> dict[str, Any]:
    """
    Enrich documents that lack sufficient ``price_history`` / ``dividend_history``.

    Persists full history arrays into ``stock_documents.document`` JSONB.
    """
    from data_ingestion.stock_enricher import create_stock_enricher
    from services.shared_market_db import get_shared_vector_store

    store = get_shared_vector_store()
    candidates = _resolve_backfill_candidates(
        store,
        symbols=symbols,
        prioritize_portfolio=prioritize_portfolio,
    )

    batch = candidates[: max(0, limit)]
    stats: dict[str, Any] = {
        "candidates": len(candidates),
        "processed": 0,
        "enriched": 0,
        "ready_after": 0,
        "errors": 0,
        "portfolio_first": prioritize_portfolio,
        "symbols": [],
        "timestamp": datetime.now().isoformat(),
    }
    if not batch:
        return stats

    enricher = create_stock_enricher(request_delay=request_delay)
    enriched: list[StockDocument] = []
    total = len(batch)

    for index, document in enumerate(batch, start=1):
        stats["processed"] += 1
        symbol = document.symbol.upper()
        if progress_callback:
            progress_callback(
                index / total,
                f"Backfilling {symbol} ({index}/{total})",
            )
        try:
            updated = enricher.enrich_document(document)
            enriched.append(updated)
            stats["enriched"] += 1
            stats["symbols"].append(symbol)
            if yield_channel_ready(updated):
                stats["ready_after"] += 1
        except Exception as exc:
            logger.warning("History backfill failed for %s: %s", symbol, exc)
            stats["errors"] += 1

    if enriched:
        store.add_documents(enriched)
        try:
            from db.connection import use_cloud_sql

            if use_cloud_sql():
                from db.postgres_market_history_store import PostgresMarketHistoryStore

                PostgresMarketHistoryStore().sync_pending_from_jsonb(
                    limit=max(len(enriched), 10),
                )
        except Exception as exc:
            logger.debug("History table sync after backfill skipped: %s", exc)
        logger.info(
            "History backfill stored %d documents (%d yield-ready)",
            len(enriched),
            stats["ready_after"],
        )

    return stats


def backfill_portfolio_holdings(
    symbols: list[str],
    *,
    request_delay: float = 0.35,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Backfill thin history for portfolio tickers before yield-chart preload."""
    unique = sorted({(symbol or "").strip().upper() for symbol in symbols if symbol})
    if not unique:
        return {
            "candidates": 0,
            "processed": 0,
            "enriched": 0,
            "ready_after": 0,
            "errors": 0,
            "symbols": [],
            "timestamp": datetime.now().isoformat(),
        }
    return backfill_thin_history(
        limit=len(unique),
        symbols=unique,
        request_delay=request_delay,
        progress_callback=progress_callback,
        prioritize_portfolio=True,
    )


def thin_history_summary(documents: list[StockDocument] | None = None) -> dict[str, int]:
    """Counts for admin dashboards."""
    if documents is None:
        try:
            from db.connection import use_cloud_sql

            if use_cloud_sql():
                from db.postgres_market_store import PostgresMarketStore

                return PostgresMarketStore().history_coverage_summary()
        except Exception:  # noqa: S110
            pass
        from services.shared_market_db import get_shared_vector_store

        documents = get_shared_vector_store().get_all_documents()

    total = len(documents)
    thin = len(documents_needing_history_backfill(documents))
    ready = sum(1 for doc in documents if yield_channel_ready(doc))
    return {
        "total": total,
        "thin_history": thin,
        "yield_ready": ready,
        "min_price_points": MIN_YIELD_PRICE_POINTS,
        "min_dividend_payments": MIN_YIELD_DIVIDEND_PAYMENTS,
    }
