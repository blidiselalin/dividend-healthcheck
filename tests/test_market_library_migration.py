"""Tests for legacy ChromaDB → PostgreSQL market library import."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from data_ingestion.models import StockDocument
from data_ingestion.vector_store import load_legacy_vectordb_documents
from services.market_library_migration import (
    import_legacy_market_library,
    pick_richer_document,
    should_auto_import,
    write_import_marker,
)


def test_load_legacy_vectordb_documents_from_fallback(tmp_path: Path):
    vdb = tmp_path / "vectordb"
    vdb.mkdir()
    doc = StockDocument(symbol="KO", name="Coca-Cola")
    payload = {doc.document_id: doc.to_full_dict()}
    (vdb / "fallback_store.json").write_text(json.dumps(payload))

    docs = load_legacy_vectordb_documents(vdb)
    assert len(docs) == 1
    assert docs[0].symbol == "KO"


def test_load_legacy_vectordb_documents_missing_dir(tmp_path: Path):
    assert load_legacy_vectordb_documents(tmp_path / "missing") == []


def test_load_legacy_vectordb_documents_empty_chroma_scaffold(tmp_path: Path):
    import chromadb
    from chromadb.config import Settings

    vdb = tmp_path / "vectordb"
    vdb.mkdir()
    client = chromadb.PersistentClient(path=str(vdb), settings=Settings(anonymized_telemetry=False))
    client.get_or_create_collection("dividend_stocks")

    assert load_legacy_vectordb_documents(vdb) == []


def _doc(symbol: str, prices: int, divs: int) -> StockDocument:
    doc = StockDocument(symbol=symbol, name=symbol)
    doc.price_history = [{"date": f"2024-01-{i:02d}", "close": 100.0} for i in range(1, prices + 1)]
    doc.dividend_history = [{"date": f"2024-0{i}-01", "amount": 1.0} for i in range(1, divs + 1)]
    return doc


def test_pick_richer_document_prefers_more_history():
    thin = _doc("AAPL", prices=10, divs=1)
    rich = _doc("AAPL", prices=300, divs=8)
    assert pick_richer_document(thin, rich) is rich
    assert pick_richer_document(rich, thin) is rich


def test_should_auto_import_when_postgres_empty(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    vdb = data_dir / "vectordb"
    vdb.mkdir(parents=True)
    doc = StockDocument(symbol="MSFT", name="Microsoft")
    (vdb / "fallback_store.json").write_text(json.dumps({doc.document_id: doc.to_full_dict()}))

    with patch("services.market_library_migration.diagnose_legacy_import") as diag_fn:
        from services.market_library_migration import LegacyImportDiagnostics

        diag_fn.return_value = LegacyImportDiagnostics(
            data_dir=data_dir,
            vectordb_dir=vdb,
            vectordb_exists=True,
            fallback_json=True,
            chroma_sqlite=False,
            chromadb_available=True,
            legacy_document_count=1,
            postgres_document_count=0,
        )
        assert should_auto_import(data_dir) is True


def test_should_auto_import_skips_when_marker_present(tmp_path: Path):
    write_import_marker(tmp_path, {"imported": 1})
    assert should_auto_import(tmp_path) is False


def test_import_legacy_market_library_writes_postgres(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vdb = data_dir / "vectordb"
    vdb.mkdir(parents=True)
    doc = StockDocument(symbol="AAPL", name="Apple")
    payload = {doc.document_id: doc.to_full_dict()}
    (vdb / "fallback_store.json").write_text(json.dumps(payload))

    mock_pg = patch("db.postgres_market_store.PostgresMarketStore")
    with patch("db.connection.use_cloud_sql", return_value=True), patch(
        "db.connection.ensure_schema"
    ), mock_pg as store_cls:
        instance = store_cls.return_value
        instance.get_all_documents.return_value = []
        instance.count.return_value = 1

        stats = import_legacy_market_library(data_dir, force=True)

    assert stats["imported"] == 1
    instance.add_documents.assert_called_once()
