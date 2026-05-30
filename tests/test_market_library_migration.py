"""Tests for legacy ChromaDB → PostgreSQL market library import."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from data_ingestion.models import StockDocument
from data_ingestion.vector_store import load_legacy_vectordb_documents
from scripts.migrate_to_cloud_sql import _import_market_library


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


def test_import_market_library_writes_postgres(tmp_path: Path, monkeypatch, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vdb = data_dir / "vectordb"
    vdb.mkdir(parents=True)
    doc = StockDocument(symbol="AAPL", name="Apple")
    payload = {doc.document_id: doc.to_full_dict()}
    (vdb / "fallback_store.json").write_text(json.dumps(payload))

    mock_pg = patch("db.postgres_market_store.PostgresMarketStore")
    with patch("db.connection.use_cloud_sql", return_value=True), mock_pg as store_cls:
        instance = store_cls.return_value
        instance.count.return_value = 1

        imported = _import_market_library(data_dir)

    assert imported == 1
    instance.add_documents.assert_called_once()
    assert "market library:" in capsys.readouterr().out
