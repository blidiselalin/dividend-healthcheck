"""Tests for multi-source stock snapshot merge (no live APIs)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from data_ingestion.deposits_store import DepositsStore
from data_ingestion.dividend_income_store import DividendIncomeStore
from data_ingestion.dividend_receipt_store import DividendReceiptStore
from data_ingestion.models import DataSource, StockDocument
from data_ingestion.providers.base import StockDataProvider
from data_ingestion.providers.composite import MultiSourceEnricher, default_providers
from data_ingestion.providers.sec_edgar import SecEdgarProvider, clear_sec_caches
from data_ingestion.providers.stooq import StooqProvider, _parse_stooq_csv, _stooq_symbol
from data_ingestion.providers.snapshot import (
    StockSnapshot,
    apply_snapshot_to_document,
    missing_field_groups,
)
from data_ingestion.providers.yahoo import YahooFinanceProvider
from data_ingestion.stock_enricher import (
    ENRICHER_AVAILABLE,
    create_stock_enricher,
    provider_status,
)
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore


class _StubProvider(StockDataProvider):
    source = DataSource.MANUAL
    field_groups = frozenset({"dividend", "price"})
    priority = 50

    def __init__(self, snapshot: StockSnapshot):
        self.snapshot = snapshot

    def available(self) -> bool:
        return True

    def fetch(self, symbol: str):
        return StockSnapshot(
            symbol=symbol.upper(),
            source=self.source,
            dividend_yield=self.snapshot.dividend_yield,
            current_price=self.snapshot.current_price,
        )


class _IdentityProvider(StockDataProvider):
    source = DataSource.SEC_EDGAR
    field_groups = frozenset({"identity"})
    priority = 20

    def available(self) -> bool:
        return True

    def fetch(self, symbol: str):
        return StockSnapshot(
            symbol=symbol.upper(),
            source=self.source,
            name="Acme Corp",
            sector="Consumer",
        )


def test_enricher_available():
    assert ENRICHER_AVAILABLE is True


def test_create_stock_enricher_returns_composite():
    enricher = create_stock_enricher(request_delay=0.1)
    assert isinstance(enricher, MultiSourceEnricher)


def test_provider_status_includes_free_providers():
    rows = {row["id"]: row for row in provider_status()}
    assert rows["yahoo"]["available"] is True
    assert rows["sec_edgar"]["available"] is True
    assert rows["stooq"]["available"] is True
    assert "finnhub" not in rows
    assert "fmp" not in rows


def test_default_providers_are_free_sources():
    providers = default_providers()
    ids = {provider.source for provider in providers}
    assert DataSource.YAHOO in ids
    assert DataSource.SEC_EDGAR in ids
    assert DataSource.STOOQ in ids
    assert DataSource.FINNHUB not in ids
    assert DataSource.FMP not in ids


def test_stooq_symbol_maps_class_shares():
    assert _stooq_symbol("BRK.B") == "brk-b.us"
    assert _stooq_symbol("KO") == "ko.us"


def test_parse_stooq_csv_builds_history():
    csv_text = (
        "Date,Open,High,Low,Close,Volume\n"
        "2024-01-02,10,11,9,10.5,1000\n"
        "2024-01-03,10.5,11.5,10,11,1200\n"
    )
    points = _parse_stooq_csv(csv_text)
    assert len(points) == 2
    assert points[-1].close == 11.0


@patch("data_ingestion.providers.sec_edgar._ticker_index", return_value={"KO": 21344})
def test_sec_edgar_fetch_parses_company_facts(mock_index):
    clear_sec_caches()
    provider = SecEdgarProvider(request_delay=0)
    facts = {
        "entityName": "Coca-Cola Co",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [{"end": "2023-12-31", "val": 1000}],
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [{"end": "2023-12-31", "val": 100}],
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [{"end": "2023-12-31", "val": 500}],
                    }
                },
            }
        },
    }
    provider._get_facts = MagicMock(return_value=facts)
    provider._submissions_sic = MagicMock(
        return_value={"code": "2080", "description": "Beverages"}
    )

    snap = provider.fetch("KO")
    assert snap is not None
    assert snap.name == "Coca-Cola Co"
    assert snap.sector == "Industrials"
    assert snap.profit_margin == 10.0
    assert snap.roe == 20.0


def test_apply_snapshot_fills_gaps_without_overwrite():
    doc = StockDocument(symbol="KO", name="KO", source=DataSource.MANUAL)
    doc.dividend_yield = 3.1
    snap = StockSnapshot(
        symbol="KO",
        source=DataSource.SEC_EDGAR,
        name="Coca-Cola",
        dividend_yield=99.0,
        current_price=60.0,
        pe_ratio=22.0,
    )
    apply_snapshot_to_document(doc, snap)
    assert doc.name == "Coca-Cola"
    assert doc.dividend_yield == 3.1
    assert doc.current_price == 60.0
    assert doc.pe_ratio == 22.0


def test_composite_calls_second_provider_for_gaps():
    doc = StockDocument(symbol="AAA", name="AAA", source=DataSource.MANUAL)
    enricher = MultiSourceEnricher(
        providers=[
            _StubProvider(StockSnapshot(symbol="AAA", current_price=10.0)),
            _IdentityProvider(),
        ],
        use_yfinance_post_process=False,
    )
    result = enricher.enrich_document(doc)
    assert result.current_price == 10.0
    assert result.name == "Acme Corp"
    assert result.sector == "Consumer"


def test_snapshot_merge_from_combines_fields():
    left = StockSnapshot(symbol="KO", source=DataSource.YAHOO)
    right = StockSnapshot(symbol="KO", source=DataSource.STOOQ, dividend_yield=3.0)
    left.merge_from(right)
    assert left.dividend_yield == 3.0
