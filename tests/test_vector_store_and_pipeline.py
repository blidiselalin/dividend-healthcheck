"""Tests for vector store batch behavior and ingestion pipeline edge cases."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data_ingestion.models import StockDocument
from data_ingestion.pipeline import DataIngestionPipeline
from data_ingestion.vector_store import VectorStore
from ingest_data import _downloads_have_ingestible_files


def test_add_documents_empty_list(tmp_path: Path) -> None:
    store = VectorStore(persist_directory=str(tmp_path / "vectordb"))
    assert store.add_documents([]) == []


def test_downloads_have_ingestible_files(tmp_path: Path) -> None:
    assert not _downloads_have_ingestible_files(tmp_path)
    (tmp_path / "stockquote").mkdir()
    assert not _downloads_have_ingestible_files(tmp_path)
    (tmp_path / "stockquote" / "fundamentals.csv").write_text("symbol,price\nKO,60\n")
    assert _downloads_have_ingestible_files(tmp_path)
    (tmp_path / "readme.txt").write_text("not ingestible")
    assert _downloads_have_ingestible_files(tmp_path)


def test_pipeline_skips_empty_batch_add(tmp_path: Path) -> None:
    mock_store = MagicMock()
    mock_store.count.return_value = 3
    mock_store.add_documents.return_value = []

    pipeline = DataIngestionPipeline(
        data_dir=str(tmp_path / "downloads"),
        vectordb_dir=str(tmp_path / "vectordb"),
    )
    pipeline.vector_store = mock_store
    pipeline.downloaders = {
        "stockquote": MagicMock(process_directory=lambda: iter(())),
        "nasdaq": MagicMock(process_directory=lambda: iter(())),
    }

    stats = pipeline.run(sources=["stockquote"], enrich_with_yfinance=False)
    mock_store.add_documents.assert_not_called()
    assert stats["documents_added"] == 0


def test_pipeline_empty_run_enrich_falls_back_to_enrich_existing(tmp_path: Path) -> None:
    pipeline = DataIngestionPipeline(
        data_dir=str(tmp_path / "downloads"),
        vectordb_dir=str(tmp_path / "vectordb"),
    )
    pipeline.downloaders = {
        "stockquote": MagicMock(process_directory=lambda: iter(())),
    }
    expected = {"enriched": 2, "total_documents": 5}
    with patch("data_ingestion.pipeline.ENRICHER_AVAILABLE", True), patch.object(
        pipeline, "enrich_existing", return_value=expected
    ) as enrich:
        stats = pipeline.run(sources=["stockquote"], enrich_with_yfinance=True)
    enrich.assert_called_once()
    assert stats == expected


def test_vector_store_fallback_add_and_get(tmp_path: Path) -> None:
    store = VectorStore(persist_directory=str(tmp_path / "fallback_vdb"))
    if not store._use_fallback:
        pytest.skip("ChromaDB installed; fallback path not active")
    doc = StockDocument(symbol="FB", name="Fallback Test")
    store.add_document(doc)
    loaded = store.get_by_symbol("FB")
    assert loaded is not None
    assert loaded.symbol == "FB"
