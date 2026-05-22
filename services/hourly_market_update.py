"""
Scheduled market refresh: live prices plus batched yfinance enrich for stale symbols.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def enrich_stale_documents(
    *,
    stale_days: int = 7,
    limit: int = 40,
    request_delay: float = 0.35,
) -> Dict[str, Any]:
    """
    Re-enrich the oldest or lowest-quality documents in the shared vector DB.

    Processes at most ``limit`` symbols per run so hourly cron stays within API limits.
    """
    from config import DELISTED_SYMBOLS, VECTORDB_DIR
    from data_ingestion.vector_store import VectorStore
    from data_ingestion.yfinance_enricher import YFinanceEnricher

    store = VectorStore(persist_directory=str(VECTORDB_DIR))
    cutoff = datetime.now() - timedelta(days=max(1, stale_days))

    candidates: List[Any] = []
    for document in store.get_all_documents():
        symbol = (document.symbol or "").upper()
        if not symbol or symbol in DELISTED_SYMBOLS:
            continue
        updated = document.last_updated or datetime.min
        quality = float(document.data_quality or 0)
        if updated < cutoff or quality < 55:
            candidates.append(document)

    candidates.sort(
        key=lambda doc: (
            doc.last_updated or datetime.min,
            float(doc.data_quality or 0),
        )
    )
    batch = candidates[: max(0, limit)]

    stats: Dict[str, Any] = {
        "candidates": len(candidates),
        "processed": 0,
        "enriched": 0,
        "errors": 0,
        "symbols": [],
        "timestamp": datetime.now().isoformat(),
    }

    if not batch:
        return stats

    enricher = YFinanceEnricher(request_delay=request_delay)
    enriched: List[Any] = []
    for document in batch:
        stats["processed"] += 1
        try:
            enriched.append(enricher.enrich_document(document))
            stats["enriched"] += 1
            stats["symbols"].append(document.symbol.upper())
        except Exception as exc:
            logger.warning("Hourly enrich failed for %s: %s", document.symbol, exc)
            stats["errors"] += 1

    if enriched:
        store.add_documents(enriched)

    return stats


def run_hourly_market_update(
    *,
    stale_days: int = 7,
    enrich_limit: int = 40,
    sp500_new_limit: int = 5,
) -> Dict[str, Any]:
    """
    Hourly job: refresh prices, add a few missing S&P tickers, enrich stale documents.
    """
    from services.db_price_refresh import refresh_vector_db_prices
    from services.sp500_peers_service import ensure_sp500_in_vectordb

    started = datetime.now()
    summary: Dict[str, Any] = {"started_at": started.isoformat()}

    logger.info("Hourly market update: refreshing prices")
    summary["prices"] = refresh_vector_db_prices()

    logger.info("Hourly market update: S&P catch-up (limit=%s)", sp500_new_limit)
    summary["sp500"] = ensure_sp500_in_vectordb(limit=sp500_new_limit)

    logger.info(
        "Hourly market update: enriching stale docs (days=%s, limit=%s)",
        stale_days,
        enrich_limit,
    )
    summary["enrich"] = enrich_stale_documents(
        stale_days=stale_days,
        limit=enrich_limit,
    )

    summary["finished_at"] = datetime.now().isoformat()
    summary["elapsed_seconds"] = round(
        (datetime.now() - started).total_seconds(), 1
    )
    return summary
