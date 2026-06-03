"""
Backwards compatibility for market data enrichment and stored documents.

Covers legacy DataSource values, YFinanceEnricher, pipeline/hourly entry points,
vector store round-trips, and deprecated aliases.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from data_ingestion.models import DataSource, StockDocument, parse_data_source
from data_ingestion.pipeline import DataIngestionPipeline
from data_ingestion.vector_store import VectorStore
from data_ingestion.yfinance_enricher import YFinanceEnricher
from services import portfolio_vector_sync as sync


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("yahoo", DataSource.YAHOO),
        ("finnhub", DataSource.FINNHUB),
        ("fmp", DataSource.FMP),
        ("sec_edgar", DataSource.SEC_EDGAR),
        ("stooq", DataSource.STOOQ),
        ("stockquote.io", DataSource.STOCKQUOTE_IO),
        ("manual", DataSource.MANUAL),
        ("", DataSource.MANUAL),
        (None, DataSource.MANUAL),
        ("unknown_vendor_xyz", DataSource.MANUAL),
    ],
)
def test_parse_data_source_legacy_and_unknown(raw, expected) -> None:
    assert parse_data_source(raw) == expected


def test_stock_document_from_dict_legacy_finnhub_source() -> None:
    payload = {
        "symbol": "KO",
        "name": "Coca-Cola",
        "source": "finnhub",
        "last_updated": datetime.now().isoformat(),
        "price_history": [],
        "dividend_history": [],
    }
    doc = StockDocument.from_dict(payload)
    assert doc.source == DataSource.FINNHUB
    assert doc.symbol == "KO"


def test_stock_document_roundtrip_preserves_legacy_fmp_source() -> None:
    original = StockDocument(
        symbol="JNJ",
        name="Johnson & Johnson",
        source=DataSource.FMP,
        dividend_yield=3.0,
    )
    restored = StockDocument.from_dict(original.to_full_dict())
    assert restored.source == DataSource.FMP
    assert restored.dividend_yield == 3.0


def test_vector_store_fallback_loads_legacy_finnhub_metadata(tmp_path) -> None:
    store = VectorStore(persist_directory=str(tmp_path / "vdb"))
    if not store._use_fallback:
        pytest.skip("ChromaDB installed; fallback path not active")

    doc = StockDocument(symbol="LEG", name="Legacy Co", source=DataSource.FINNHUB)
    store.add_document(doc)
    loaded = store.get_by_symbol("LEG")
    assert loaded is not None
    assert loaded.source == DataSource.FINNHUB


@patch("data_ingestion.yfinance_enricher.YFINANCE_AVAILABLE", True)
@patch.object(YFinanceEnricher, "_enrich_price_data")
@patch.object(YFinanceEnricher, "_enrich_dividend_history")
@patch.object(
    YFinanceEnricher,
    "_get_info_safe",
    return_value={
        "longName": "Coca-Cola Co",
        "sector": "Consumer Defensive",
        "currentPrice": 60.0,
        "dividendYield": 0.03,
    },
)
def test_yfinance_enricher_still_enriches_gaps(_info, _div, _price) -> None:
    enricher = YFinanceEnricher(request_delay=0)
    _div.side_effect = lambda doc, ticker: doc
    _price.side_effect = lambda doc, ticker: doc
    doc = StockDocument(symbol="KO", name="KO", source=DataSource.MANUAL)
    result = enricher.enrich_document(doc)
    assert result.name == "Coca-Cola Co"
    assert result.source == DataSource.YAHOO


@patch("data_ingestion.pipeline.create_stock_enricher")
def test_pipeline_enrich_uses_stock_enricher(mock_create, tmp_path) -> None:
    mock_enricher = MagicMock()
    mock_enricher.enrich_batch.return_value = [
        StockDocument(symbol="KO", name="Coca-Cola", source=DataSource.YAHOO)
    ]
    mock_create.return_value = mock_enricher

    pipeline = DataIngestionPipeline(
        data_dir=str(tmp_path / "downloads"),
        vectordb_dir=str(tmp_path / "vectordb"),
    )
    pipeline.downloaders = {
        "stockquote": MagicMock(
            process_directory=lambda: iter(
                [StockDocument(symbol="KO", name="KO", source=DataSource.MANUAL)]
            )
        ),
    }
    pipeline.vector_store = MagicMock()
    pipeline.vector_store.add_documents.return_value = ["id1"]

    pipeline.run(sources=["stockquote"], enrich_with_yfinance=True)

    mock_create.assert_called_once()
    mock_enricher.enrich_batch.assert_called_once()


def test_multi_source_enricher_post_process_uses_yfinance_legacy() -> None:
    from data_ingestion.providers.composite import MultiSourceEnricher
    from data_ingestion.providers.snapshot import StockSnapshot

    enricher = MultiSourceEnricher(providers=[], use_yfinance_post_process=True)
    doc = StockDocument(symbol="KO", name="KO", source=DataSource.MANUAL)
    legacy_doc = StockDocument(symbol="KO", name="Coca-Cola Co", source=DataSource.YAHOO)

    with patch.object(
        enricher,
        "fetch_snapshot",
        return_value=StockSnapshot(symbol="KO", current_price=55.0),
    ):
        with patch.object(enricher._legacy, "enrich_document", return_value=legacy_doc) as mock_legacy:
            result = enricher.enrich_document(doc)

    mock_legacy.assert_called_once()
    assert result.name == "Coca-Cola Co"


def test_multi_source_enricher_can_disable_yfinance_post_process() -> None:
    from data_ingestion.providers.composite import MultiSourceEnricher
    from data_ingestion.providers.snapshot import StockSnapshot

    enricher = MultiSourceEnricher(providers=[], use_yfinance_post_process=False)
    doc = StockDocument(symbol="X", name="X", source=DataSource.MANUAL)
    with patch.object(
        enricher,
        "fetch_snapshot",
        return_value=StockSnapshot(symbol="X", current_price=1.0),
    ):
        with patch.object(enricher._legacy, "enrich_document") as mock_legacy:
            enricher.enrich_document(doc)
    mock_legacy.assert_not_called()


def test_remove_delisted_from_vector_db_alias() -> None:
    from services.db_price_refresh import (
        remove_delisted_from_market_library,
        remove_delisted_from_vector_db,
    )

    with patch("services.db_price_refresh.remove_delisted_from_market_library") as mock:
        mock.return_value = {"removed": 1}
        assert remove_delisted_from_vector_db(["ZZ"]) == {"removed": 1}
    mock.assert_called_once_with(["ZZ"])


@patch("data_ingestion.stock_enricher.create_stock_enricher")
def test_portfolio_vector_sync_fetch_uses_stock_enricher(mock_create) -> None:
    mock_enricher = MagicMock()
    expected = StockDocument(symbol="NEW", name="New Co", source=DataSource.YAHOO)
    mock_enricher.fetch_document.return_value = expected
    mock_create.return_value = mock_enricher

    store = MagicMock()
    store.get_by_symbol.return_value = None

    ctx = MagicMock()
    ctx.portfolio.list_holdings.return_value = []

    result = sync._fetch_or_create_document(
        "NEW",
        store,
        ctx,
        enrich_missing=True,
    )
    assert result is expected
    mock_create.assert_called_once()


def test_import_stock_enricher_public_api() -> None:
    from data_ingestion import stock_enricher

    assert hasattr(stock_enricher, "create_stock_enricher")
    assert hasattr(stock_enricher, "provider_status")
    assert hasattr(stock_enricher, "ENRICHER_AVAILABLE")
