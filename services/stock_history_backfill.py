"""
Backfill thin price/dividend history in the shared market library.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from config import MIN_YIELD_DIVIDEND_PAYMENTS, MIN_YIELD_PRICE_POINTS
from utils.stock_document_history import history_is_thin, yield_channel_ready

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]


def documents_needing_history_backfill(documents: List["StockDocument"]) -> List["StockDocument"]:
    """Symbols missing enough price/dividend rows for yield channels."""
    from config import DELISTED_SYMBOLS

    thin: List[StockDocument] = []
    for document in documents:
        symbol = (document.symbol or "").upper()
        if not symbol or symbol in DELISTED_SYMBOLS:
            continue
        if history_is_thin(document):
            thin.append(document)
    thin.sort(
        key=lambda doc: (
            len(doc.price_history or []),
            len(doc.dividend_history or []),
            doc.last_updated or datetime.min,
        )
    )
    return thin


def backfill_thin_history(
    *,
    limit: int = 40,
    symbols: Optional[List[str]] = None,
    request_delay: float = 0.35,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """
    Enrich documents that lack sufficient ``price_history`` / ``dividend_history``.

    Persists full history arrays into ``stock_documents.document`` JSONB.
    """
    from data_ingestion.stock_enricher import create_stock_enricher
    from services.shared_market_db import get_shared_vector_store

    store = get_shared_vector_store()
    if symbols:
        wanted = {symbol.strip().upper() for symbol in symbols}
        candidates = [
            store.get_by_symbol(symbol)
            for symbol in sorted(wanted)
        ]
        candidates = [doc for doc in candidates if doc is not None and history_is_thin(doc)]
    else:
        candidates = documents_needing_history_backfill(store.get_all_documents())

    batch = candidates[: max(0, limit)]
    stats: Dict[str, Any] = {
        "candidates": len(candidates),
        "processed": 0,
        "enriched": 0,
        "ready_after": 0,
        "errors": 0,
        "symbols": [],
        "timestamp": datetime.now().isoformat(),
    }
    if not batch:
        return stats

    enricher = create_stock_enricher(request_delay=request_delay)
    enriched: List[StockDocument] = []
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


def thin_history_summary(documents: Optional[List["StockDocument"]] = None) -> Dict[str, int]:
    """Counts for admin dashboards."""
    if documents is None:
        try:
            from db.connection import use_cloud_sql

            if use_cloud_sql():
                from db.postgres_market_store import PostgresMarketStore

                return PostgresMarketStore().history_coverage_summary()
        except Exception:
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
