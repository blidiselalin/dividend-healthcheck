"""Tests for DB-first enhanced stock service."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import datetime, timedelta

from models.stock import DividendHistory, StockData
from services.enhanced_stock_service import EnhancedStockService


class _FakeVectorStore:
    def __init__(self, docs: dict[str, object]) -> None:
        self._docs = docs

    def count(self) -> int:
        return len(self._docs)

    def get_by_symbol(self, symbol: str):
        return self._docs.get(symbol)


def _stock(symbol: str, *, complete: bool = True, fresh: bool = True) -> StockData:
    data = StockData(
        symbol=symbol,
        name=symbol,
        sector="Consumer",
        industry="Beverages",
        price=60.0,
        dividend_yield_pct=3.0 if complete else None,
        dividend_rate=1.8 if complete else None,
        trailing_pe=20.0 if complete else None,
        payout_ratio_pct=65.0 if complete else None,
        dividend_history=DividendHistory(60, 60, 6.0, 5.0, 1.8),
        data_sources=["Vector DB"],
    )
    data._last_updated = datetime.now() - (timedelta(days=1) if fresh else timedelta(days=30))
    return data


def test_fetch_prefers_fresh_complete_db(monkeypatch) -> None:
    db_data = _stock("KO", complete=True, fresh=True)
    monkeypatch.setattr(
        "services.enhanced_stock_service.VectorStore",
        lambda persist_directory: _FakeVectorStore({"KO": object()}),
    )
    monkeypatch.setattr(
        "services.enhanced_stock_service.document_to_stock_data",
        lambda doc: db_data,
    )

    api_called = {"count": 0}

    def _api_fetch(_symbol: str):
        api_called["count"] += 1
        return None

    monkeypatch.setattr("services.enhanced_stock_service.StockService.fetch", _api_fetch)

    service = EnhancedStockService(fetch_realtime_prices=False)
    result = service.fetch("ko")

    assert result is db_data
    assert api_called["count"] == 0


def test_fetch_falls_back_to_api_when_db_incomplete(monkeypatch) -> None:
    db_data = _stock("KO", complete=False, fresh=True)
    api_data = _stock("KO", complete=True, fresh=True)
    monkeypatch.setattr(
        "services.enhanced_stock_service.VectorStore",
        lambda persist_directory: _FakeVectorStore({"KO": object()}),
    )
    monkeypatch.setattr(
        "services.enhanced_stock_service.document_to_stock_data",
        lambda doc: db_data,
    )
    monkeypatch.setattr("services.enhanced_stock_service.StockService.fetch", lambda _symbol: api_data)

    service = EnhancedStockService(fetch_realtime_prices=False)
    result = service.fetch("KO")

    assert result is api_data
    assert "Enhanced: Vector DB" in (result.data_sources or [])


def test_fetch_returns_incomplete_db_if_api_fails(monkeypatch) -> None:
    db_data = _stock("KO", complete=False, fresh=False)
    monkeypatch.setattr(
        "services.enhanced_stock_service.VectorStore",
        lambda persist_directory: _FakeVectorStore({"KO": object()}),
    )
    monkeypatch.setattr(
        "services.enhanced_stock_service.document_to_stock_data",
        lambda doc: db_data,
    )
    monkeypatch.setattr("services.enhanced_stock_service.StockService.fetch", lambda _symbol: None)

    service = EnhancedStockService(fetch_realtime_prices=False)
    result = service.fetch("KO")

    assert result is db_data
    assert result.data_sources == ["Vector DB (incomplete)"]
