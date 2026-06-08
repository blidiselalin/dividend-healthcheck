"""
One-time import of legacy Chroma / fallback JSON into PostgreSQL ``stock_documents``.

Runtime with ``DATABASE_URL`` never reads ``/data/vectordb`` — this module is the
bridge to a single Postgres dataset.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

IMPORT_MARKER = ".market_library_imported.json"


@dataclass
class LegacyImportDiagnostics:
    data_dir: Path
    vectordb_dir: Path
    vectordb_exists: bool
    fallback_json: bool
    chroma_sqlite: bool
    chromadb_available: bool
    legacy_document_count: int = 0
    postgres_document_count: int = 0
    postgres_ready_for_yield: int = 0
    message: str = ""
    extra_paths_checked: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_dir": str(self.data_dir),
            "vectordb_dir": str(self.vectordb_dir),
            "vectordb_exists": self.vectordb_exists,
            "fallback_json": self.fallback_json,
            "chroma_sqlite": self.chroma_sqlite,
            "chromadb_available": self.chromadb_available,
            "legacy_document_count": self.legacy_document_count,
            "postgres_document_count": self.postgres_document_count,
            "postgres_ready_for_yield": self.postgres_ready_for_yield,
            "message": self.message,
            "extra_paths_checked": list(self.extra_paths_checked),
        }


def candidate_vectordb_dirs(data_dir: Path) -> List[Path]:
    """Search order for legacy market library files."""
    data_dir = data_dir.expanduser()
    candidates = [
        data_dir / "vectordb",
        data_dir / "data" / "vectordb",
    ]
    home = Path.home() / ".dividendscope" / "data" / "vectordb"
    if home not in candidates:
        candidates.append(home)
    seen: set[str] = set()
    ordered: List[Path] = []
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


def _chroma_present(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "chroma.sqlite3").is_file():
        return True
    return any(
        child.is_dir() and (child / "chroma.sqlite3").is_file()
        for child in path.iterdir()
    )


def diagnose_legacy_import(data_dir: Path) -> LegacyImportDiagnostics:
    """Explain why legacy Chroma may not have reached PostgreSQL."""
    from data_ingestion.vector_store import CHROMADB_AVAILABLE, load_legacy_vectordb_documents

    data_dir = data_dir.expanduser()
    checked: List[str] = []
    vectordb_dir = data_dir / "vectordb"
    legacy_docs: List[Any] = []

    for candidate in candidate_vectordb_dirs(data_dir):
        checked.append(str(candidate))
        if not candidate.is_dir():
            continue
        docs = load_legacy_vectordb_documents(candidate)
        if docs:
            vectordb_dir = candidate
            legacy_docs = docs
            break

    diag = LegacyImportDiagnostics(
        data_dir=data_dir,
        vectordb_dir=vectordb_dir,
        vectordb_exists=vectordb_dir.is_dir(),
        fallback_json=(vectordb_dir / "fallback_store.json").is_file(),
        chroma_sqlite=_chroma_present(vectordb_dir),
        chromadb_available=CHROMADB_AVAILABLE,
        legacy_document_count=len(legacy_docs),
        extra_paths_checked=checked,
    )

    try:
        from db.connection import use_cloud_sql
        from db.postgres_market_store import PostgresMarketStore

        if use_cloud_sql():
            store = PostgresMarketStore()
            diag.postgres_document_count = store.count()
            coverage = store.history_coverage_summary()
            diag.postgres_ready_for_yield = coverage["yield_ready"]
    except Exception as exc:
        logger.debug("Postgres diagnostics unavailable: %s", exc)

    if not diag.vectordb_exists:
        diag.message = (
            f"No legacy vectordb directory under {data_dir}. "
            "Copy local ~/.dividendscope/data/vectordb to /data/vectordb on the server, "
            "or rsync with --include-vectordb, then run migrate."
        )
    elif diag.legacy_document_count == 0:
        if diag.fallback_json:
            diag.message = "fallback_store.json exists but parsed 0 documents — file may be empty or corrupt."
        elif diag.chroma_sqlite and not diag.chromadb_available:
            diag.message = "Chroma files found but chromadb package unavailable in this environment."
        elif diag.chroma_sqlite:
            diag.message = "Chroma database exists but all collections are empty — run local ingest first."
        else:
            diag.message = f"Directory {vectordb_dir} exists but contains no Chroma or fallback_store.json."
    elif diag.postgres_document_count == 0:
        diag.message = (
            f"Found {diag.legacy_document_count} legacy documents but PostgreSQL stock_documents is empty — "
            "run: python scripts/migrate_to_cloud_sql.py --data-dir /data"
        )
    elif diag.postgres_ready_for_yield < diag.legacy_document_count:
        diag.message = (
            f"PostgreSQL has {diag.postgres_document_count} symbols but only "
            f"{diag.postgres_ready_for_yield} are yield-ready; legacy has {diag.legacy_document_count} — "
            "re-import with merge to restore history."
        )
    else:
        diag.message = "Legacy and PostgreSQL both appear populated."

    return diag


def _history_score(doc: Any) -> tuple[int, int, float]:
    from utils.stock_document_history import history_counts

    prices, divs = history_counts(doc)
    quality = float(getattr(doc, "data_quality", 0) or 0)
    return prices, divs, quality


def pick_richer_document(existing: Any, incoming: Any) -> Any:
    """Prefer the record with more price/dividend history (typical Chroma vs thin ingest)."""
    if existing is None:
        return incoming
    if incoming is None:
        return existing

    ex_score = _history_score(existing)
    in_score = _history_score(incoming)
    if in_score[:2] > ex_score[:2]:
        return incoming
    if in_score[:2] < ex_score[:2]:
        return existing

    ex_updated = getattr(existing, "last_updated", None) or datetime.min
    in_updated = getattr(incoming, "last_updated", None) or datetime.min
    if in_updated > ex_updated:
        return incoming
    if in_score[2] > ex_score[2]:
        return incoming
    return existing


def import_marker_path(data_dir: Path) -> Path:
    return data_dir.expanduser() / IMPORT_MARKER


def import_already_recorded(data_dir: Path) -> bool:
    path = import_marker_path(data_dir)
    return path.is_file()


def write_import_marker(data_dir: Path, stats: Dict[str, Any]) -> None:
    path = import_marker_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"finished_at": datetime.now().isoformat(timespec="seconds"), **stats}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def import_legacy_market_library(
    data_dir: Path,
    *,
    vectordb_dir: Optional[Path] = None,
    merge_with_postgres: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Import legacy Chroma/fallback JSON into PostgreSQL ``stock_documents``.

    Returns stats dict (imported, merged, skipped, errors, diagnostics).
    """
    from data_ingestion.vector_store import load_legacy_vectordb_documents
    from db.connection import ensure_schema, use_cloud_sql
    from db.postgres_market_store import PostgresMarketStore
    from utils.stock_document_history import hydrate_document_history, yield_channel_ready

    data_dir = data_dir.expanduser()
    stats: Dict[str, Any] = {
        "imported": 0,
        "merged": 0,
        "skipped": 0,
        "errors": 0,
        "legacy_source": None,
        "postgres_before": 0,
        "postgres_after": 0,
        "yield_ready_after": 0,
    }

    if not use_cloud_sql():
        stats["message"] = "DATABASE_URL not set — cannot import into PostgreSQL"
        return stats

    ensure_schema()
    diag = diagnose_legacy_import(data_dir)
    stats["diagnostics"] = diag.to_dict()
    stats["postgres_before"] = diag.postgres_document_count

    if not force and import_already_recorded(data_dir) and diag.postgres_document_count > 0:
        if diag.legacy_document_count <= diag.postgres_ready_for_yield:
            stats["message"] = "Import marker present and Postgres looks complete — use --force to re-import"
            stats["skipped"] = diag.legacy_document_count
            return stats

    source = vectordb_dir
    if source is None:
        for candidate in candidate_vectordb_dirs(data_dir):
            if candidate.is_dir() and load_legacy_vectordb_documents(candidate):
                source = candidate
                break
        if source is None:
            source = data_dir / "vectordb"

    stats["legacy_source"] = str(source)
    legacy_docs = load_legacy_vectordb_documents(source)
    legacy_docs = [hydrate_document_history(doc) for doc in legacy_docs]

    if not legacy_docs:
        stats["message"] = diag.message or "No legacy documents found"
        return stats

    store = PostgresMarketStore()
    existing_by_symbol: Dict[str, Any] = {}
    if merge_with_postgres:
        for doc in store.get_all_documents():
            if doc.symbol:
                existing_by_symbol[doc.symbol.upper()] = doc

    to_write: List[Any] = []
    for doc in legacy_docs:
        sym = (doc.symbol or "").upper()
        if not sym:
            stats["errors"] += 1
            continue
        if merge_with_postgres and sym in existing_by_symbol:
            merged = pick_richer_document(existing_by_symbol[sym], doc)
            if merged is doc:
                stats["merged"] += 1
            else:
                stats["skipped"] += 1
                continue
            to_write.append(merged)
        else:
            to_write.append(doc)
            stats["imported"] += 1

    if to_write:
        store.add_documents(to_write)

    all_after = store.get_all_documents()
    stats["postgres_after"] = len(all_after)
    stats["yield_ready_after"] = sum(1 for doc in all_after if yield_channel_ready(doc))
    stats["message"] = (
        f"Wrote {len(to_write)} documents from {source} "
        f"(Postgres {stats['postgres_before']} → {stats['postgres_after']}, "
        f"yield-ready {stats['yield_ready_after']})"
    )
    write_import_marker(
        data_dir,
        {
            "legacy_source": stats["legacy_source"],
            "written": len(to_write),
            **{k: stats[k] for k in ("imported", "merged", "skipped", "errors", "postgres_after", "yield_ready_after")},
        },
    )
    logger.info("Legacy market library import: %s", stats["message"])
    return stats


def should_auto_import(data_dir: Path) -> bool:
    """True when legacy files exist but Postgres is empty or mostly missing history."""
    import os

    if os.environ.get("DIVIDENDSCOPE_SKIP_LEGACY_IMPORT", "").strip().lower() in ("1", "true", "yes"):
        return False
    if import_already_recorded(data_dir):
        return False
    diag = diagnose_legacy_import(data_dir)
    if diag.legacy_document_count == 0:
        return False
    if diag.postgres_document_count == 0:
        return True
    if diag.postgres_ready_for_yield < max(1, diag.legacy_document_count // 2):
        return True
    return False
