"""
Shared market library — analysed S&P stock documents for all users.

Production (DATABASE_URL set): PostgreSQL ``stock_documents`` table.
Local dev without Postgres: ChromaDB under ``VECTORDB_DIR``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from config import VECTORDB_DIR

    SHARED_MARKET_DB_DIR = VECTORDB_DIR
except ImportError:
    SHARED_MARKET_DB_DIR = Path("data/vectordb")

_store_instance: Optional[Any] = None


def shared_market_db_path() -> Path:
    """Legacy path label for local Chroma; unused at runtime when Postgres is configured."""
    return Path(SHARED_MARKET_DB_DIR)


def _vector_store_class():
    from data_ingestion.vector_store import VectorStore

    return VectorStore


def get_shared_vector_store():
    """Return the shared market library store (PostgreSQL or local Chroma)."""
    global _store_instance
    if _store_instance is None:
        VectorStore = _vector_store_class()
        path = str(shared_market_db_path())
        _store_instance = VectorStore(persist_directory=path)
        count = _store_instance.count()
        logger.info("Shared market library (%s documents)", count)
    return _store_instance


def reset_shared_vector_store_cache() -> None:
    global _store_instance
    _store_instance = None


def document_count() -> int:
    try:
        return get_shared_vector_store().count()
    except Exception:
        return 0


def shared_market_db_status() -> Dict[str, Any]:
    """Status for UI and startup logs (same for every logged-in user)."""
    from db.connection import use_cloud_sql

    count = document_count()
    storage = "postgresql" if use_cloud_sql() else "local"
    status: Dict[str, Any] = {
        "path": "postgresql:stock_documents" if use_cloud_sql() else str(shared_market_db_path()),
        "storage": storage,
        "document_count": count,
        "populated": count > 0,
        "sp500_coverage": None,
    }
    if count > 0:
        try:
            from services.sp500_peers_service import coverage_stats

            status["sp500_coverage"] = coverage_stats()
        except Exception as exc:
            logger.debug("S&P coverage stats unavailable: %s", exc)
    return status


def get_document(symbol: str):
    """Lookup one symbol in the shared library (any user)."""
    try:
        return get_shared_vector_store().get_by_symbol(symbol.upper())
    except Exception:
        return None
