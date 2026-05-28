"""
Shared market database (ChromaDB) — one copy for all users.

Holds S&P 500 historical prices, dividends, and fundamentals. Lives at
``VECTORDB_DIR`` (e.g. ``/data/vectordb`` on Docker). Per-user SQLite only
stores portfolio positions; everyone reads the same analysed library.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from config import VECTORDB_DIR

    SHARED_MARKET_DB_DIR = VECTORDB_DIR
except ImportError:
    SHARED_MARKET_DB_DIR = Path("data/vectordb")

# Optional seed baked into the image at build time (copy to volume on first boot)
BUNDLED_MARKET_DB_DIR = Path(__file__).resolve().parent.parent / "data" / "vectordb"

_store_instance: Optional[Any] = None


def shared_market_db_path() -> Path:
    return Path(SHARED_MARKET_DB_DIR)


def legacy_vectordb_search_paths(*preferred: Path) -> list[Path]:
    """Candidate on-disk Chroma locations, in priority order."""
    ordered: list[Path] = []
    seen: set[str] = set()
    for raw in (*preferred, shared_market_db_path(), BUNDLED_MARKET_DB_DIR):
        path = Path(raw)
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen or not path.is_dir():
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def legacy_vectordb_document_count(directory: Path) -> int:
    from data_ingestion.vector_store import load_legacy_vectordb_documents

    return len(load_legacy_vectordb_documents(directory))


def _vector_store_class():
    from data_ingestion.vector_store import VectorStore

    return VectorStore


def get_shared_vector_store():
    """Return a VectorStore pointed at the global analysed-stocks directory."""
    global _store_instance
    if _store_instance is None:
        VectorStore = _vector_store_class()
        path = str(shared_market_db_path())
        _store_instance = VectorStore(persist_directory=path)
        count = _store_instance.count()
        logger.info("Shared market DB at %s (%d documents)", path, count)
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
    path = shared_market_db_path()
    count = document_count()
    status: Dict[str, Any] = {
        "path": str(path),
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


def bootstrap_shared_market_db_from_bundle() -> bool:
    """
    Copy bundled ``data/vectordb`` into the runtime data dir when the volume is empty.

    Used on first Docker boot so a pre-ingested image can seed ``/data/vectordb``.
    Returns True when files were copied.
    """
    target = shared_market_db_path()
    bundle = BUNDLED_MARKET_DB_DIR

    if legacy_vectordb_document_count(target) > 0:
        return False
    if legacy_vectordb_document_count(bundle) == 0:
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(bundle, target)
    reset_shared_vector_store_cache()
    logger.info("Bootstrapped shared market DB from %s → %s", bundle, target)
    return True


def import_legacy_vectordb_to_postgres(source_dir: Path | None = None) -> int:
    """Upsert legacy Chroma/fallback documents into PostgreSQL stock_documents."""
    from db.connection import use_cloud_sql

    if not use_cloud_sql():
        return 0

    from data_ingestion.vector_store import load_legacy_vectordb_documents
    from db.postgres_market_store import PostgresMarketStore

    preferred = [Path(source_dir)] if source_dir else []
    for source in legacy_vectordb_search_paths(*preferred):
        documents = load_legacy_vectordb_documents(source)
        if not documents:
            logger.info("No legacy market library documents at %s", source)
            continue

        pg = PostgresMarketStore()
        pg.add_documents(documents)
        logger.info(
            "Imported %s stock documents from %s into PostgreSQL (total=%s)",
            len(documents),
            source,
            pg.count(),
        )
        return len(documents)

    return 0


def bootstrap_shared_market_db_to_postgres() -> int:
    """Import legacy Chroma on disk when PostgreSQL stock_documents is empty."""
    from db.connection import use_cloud_sql

    if not use_cloud_sql():
        return 0

    from db.postgres_market_store import PostgresMarketStore

    pg = PostgresMarketStore()
    if pg.count() > 0:
        return 0

    return import_legacy_vectordb_to_postgres()


def get_document(symbol: str):
    """Lookup one symbol in the shared library (any user)."""
    try:
        return get_shared_vector_store().get_by_symbol(symbol.upper())
    except Exception:
        return None
