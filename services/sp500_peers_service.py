"""
Ensure S&P 500 coverage in analysed stocks and pick same-sector peers for portfolio comparison.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from config import DELISTED_SYMBOLS
from services.shared_market_db import get_shared_vector_store
from data_ingestion.models import DataSource, StockDocument
from data_ingestion.sp500_universe import (
    get_sp500_symbols,
    sectors_match,
    sp500_symbol_set,
    yahoo_ticker,
)
from models.stock import StockData
from services.scoring import ScoringService
from utils.converters import document_to_stock_data

logger = logging.getLogger(__name__)

try:
    from data_ingestion.vector_store import VectorStore

    VECTOR_STORE_AVAILABLE = True
except ImportError:
    VECTOR_STORE_AVAILABLE = False


def _store() -> Optional["VectorStore"]:
    if not VECTOR_STORE_AVAILABLE:
        return None
    try:
        return get_shared_vector_store()
    except Exception as exc:
        logger.warning("Vector store unavailable: %s", exc)
        return None


_coverage_cache: Optional[Dict[str, Any]] = None


def coverage_stats(*, force: bool = False) -> Dict[str, Any]:
    """How many S&P 500 names exist in analysed stocks (cached per process)."""
    global _coverage_cache
    if _coverage_cache is not None and not force:
        return dict(_coverage_cache)

    universe = sp500_symbol_set()
    store = _store()
    if store is None:
        return {
            "universe_total": len(universe),
            "analysed_sp500": 0,
            "analysed_total": 0,
            "pct_covered": 0.0,
        }

    analysed_symbols = {
        doc.symbol.upper() for doc in store.get_all_documents() if doc.symbol
    }
    sp500_analysed = analysed_symbols & universe
    total = store.count()
    universe_total = len(universe)
    result = {
        "universe_total": universe_total,
        "analysed_sp500": len(sp500_analysed),
        "analysed_total": total,
        "pct_covered": (len(sp500_analysed) / universe_total * 100) if universe_total else 0.0,
    }
    _coverage_cache = result
    return dict(result)


def ensure_sp500_in_vectordb(
    *,
    limit: Optional[int] = None,
    request_delay: float = 0.35,
    progress_callback=None,
) -> Dict[str, int]:
    """
    Create and enrich missing S&P 500 documents in analysed stocks.

    Args:
        limit: Max new symbols to fetch this run (None = all missing).
    """
    stats = {"created": 0, "skipped": 0, "errors": 0, "already_present": 0}
    store = _store()
    if store is None:
        stats["errors"] = 1
        return stats

    universe = get_sp500_symbols()
    existing = {doc.symbol.upper() for doc in store.get_all_documents()}
    missing = [
        symbol
        for symbol in universe
        if symbol.upper() not in existing and symbol.upper() not in DELISTED_SYMBOLS
    ]
    if limit is not None:
        missing = missing[: max(0, limit)]

    if not missing:
        stats["already_present"] = len(universe)
        return stats

    try:
        from data_ingestion.stock_enricher import create_stock_enricher
    except ImportError:
        stats["errors"] = len(missing)
        return stats

    enricher = create_stock_enricher(request_delay=request_delay)
    total = len(missing)
    batch: List[StockDocument] = []

    for index, symbol in enumerate(missing, start=1):
        if progress_callback:
            progress_callback(f"S&P 500: {symbol}", index, total)
        try:
            document = enricher.fetch_document(symbol)
            if document is None:
                document = StockDocument(
                    symbol=symbol,
                    name=symbol,
                    source=DataSource.YAHOO,
                )
            else:
                document.source = DataSource.YAHOO
            batch.append(document)
            stats["created"] += 1
        except Exception as exc:
            logger.warning("S&P 500 ingest failed for %s: %s", symbol, exc)
            stats["errors"] += 1

        if len(batch) >= 25:
            store.add_documents(batch)
            batch.clear()

    if batch:
        store.add_documents(batch)

    stats["already_present"] = len(existing & set(universe))
    return stats


def _interest_score(data: StockData, peer_score: int) -> float:
    """Higher = more interesting as a buy/compare candidate."""
    score = float(peer_score)
    if data.dividend_yield_pct and 1.5 <= data.dividend_yield_pct <= 7:
        score += 12
    if data.dividend_history and data.dividend_history.consecutive_years >= 10:
        score += min(20, data.dividend_history.consecutive_years / 2)
    if (
        data.dividend_history
        and data.dividend_history.cagr_5y
        and data.dividend_history.cagr_5y >= 5
    ):
        score += 8
    if data.dividend_safety_score and data.dividend_safety_score >= 60:
        score += 6
    if data.payout_ratio_pct and 30 <= data.payout_ratio_pct <= 65:
        score += 4
    return score


def find_sector_peers(
    *,
    sector: str,
    exclude_symbols: Optional[List[str]] = None,
    portfolio_symbols: Optional[Set[str]] = None,
    max_peers: int = 3,
) -> List[Dict[str, Any]]:
    """
    Return 2–3 analysed S&P 500 stocks in the same sector, ranked by dividend interest.
    """
    if not sector or sector.strip().lower() in {"unknown", "n/a", ""}:
        return []

    store = _store()
    if store is None:
        return []

    universe = sp500_symbol_set()
    exclude = {yahoo_ticker(symbol) for symbol in (exclude_symbols or [])}
    portfolio = {yahoo_ticker(symbol) for symbol in (portfolio_symbols or set())}

    candidates: List[Dict[str, Any]] = []
    for doc in store.get_all_documents():
        symbol = doc.symbol.upper()
        if symbol not in universe:
            continue
        if symbol in exclude or symbol in portfolio:
            continue
        if not sectors_match(sector, doc.sector or ""):
            continue

        data = document_to_stock_data(doc)
        if not data.dividend_yield_pct or data.dividend_yield_pct <= 0:
            continue
        if data.dividend_yield_pct > 10:
            continue

        peer_score = ScoringService.calculate_score(data)
        div_streak = (
            data.dividend_history.consecutive_years if data.dividend_history else None
        )
        div_cagr = data.dividend_history.cagr_5y if data.dividend_history else None
        candidates.append(
            {
                "symbol": data.symbol,
                "name": data.name,
                "score": peer_score,
                "interest": _interest_score(data, peer_score),
                "dividend_yield_pct": data.dividend_yield_pct,
                "trailing_pe": data.trailing_pe,
                "payout_ratio_pct": data.payout_ratio_pct,
                "roe_pct": data.roe_pct,
                "debt_to_equity": data.debt_to_equity,
                "div_streak": div_streak,
                "div_cagr": div_cagr,
                "dividend_tier": data.dividend_tier,
                "is_dividend_king": data.is_dividend_king,
                "is_sp500_peer": True,
                "has_history": bool(div_streak and div_streak >= 5),
                "yield_quality": 0.0,
            }
        )

    candidates.sort(
        key=lambda row: (row.get("has_history", False), row["interest"], row["score"]),
        reverse=True,
    )
    return candidates[:max_peers]
