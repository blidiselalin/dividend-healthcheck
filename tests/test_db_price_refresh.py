"""Tests for shared market DB price refresh service."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from data_ingestion.models import PriceHistory, StockDocument
from services import db_price_refresh


def test_apply_latest_price_updates_existing_today_row() -> None:
    doc = StockDocument(symbol="KO", name="Coca-Cola")
    doc.price_history = [
        PriceHistory(date=date.today(), open=10.0, high=11.0, low=9.0, close=10.5, volume=100),
        PriceHistory(date=date(2024, 1, 1), open=8.0, high=9.0, low=7.5, close=8.5, volume=90),
    ]

    db_price_refresh._apply_latest_price(doc, 12.0)

    today = doc.price_history[0]
    assert today.close == 12.0
    assert today.high == 12.0
    assert today.low == 9.0
    assert doc.current_price == 12.0


def test_apply_latest_price_appends_when_today_missing() -> None:
    doc = StockDocument(symbol="KO", name="Coca-Cola")
    doc.price_history = [
        PriceHistory(date=date(2024, 1, 2), open=10.0, high=11.0, low=9.0, close=10.5, volume=100),
    ]

    db_price_refresh._apply_latest_price(doc, 15.0)

    assert doc.price_history[0].date == date.today()
    assert doc.price_history[0].close == 15.0


def test_refresh_market_library_prices_updates_and_skips(monkeypatch) -> None:
    doc_ko = StockDocument(symbol="KO", name="KO")
    doc_ko.price_history = []
    doc_jnj = StockDocument(symbol="JNJ", name="JNJ")
    doc_jnj.price_history = []

    class _Store:
        def __init__(self) -> None:
            self.docs = [doc_ko, doc_jnj]
            self.saved: list[StockDocument] = []

        def get_all_documents(self):
            return self.docs

        def add_documents(self, docs):
            self.saved = list(docs)

    store = _Store()
    monkeypatch.setattr("services.shared_market_db.get_shared_vector_store", lambda: store)
    monkeypatch.setattr(
        db_price_refresh,
        "_fetch_latest_price",
        lambda symbol: {"KO": 61.5, "JNJ": None, "MISSING": 12.0}[symbol],
    )

    stats = db_price_refresh.refresh_market_library_prices(
        symbols=["KO", "JNJ", "MISSING"],
        max_workers=1,
    )

    assert stats["total"] == 3
    assert stats["updated"] == 1
    assert stats["skipped"] == 2  # JNJ no price + MISSING no document
    assert stats["errors"] == 0
    assert [d.symbol for d in store.saved] == ["KO"]
    assert doc_ko.current_price == 61.5


def test_remove_delisted_from_market_library_uses_sorted_symbols(monkeypatch) -> None:
    called = {}

    class _Store:
        def delete_symbols(self, symbols):
            called["symbols"] = symbols
            return 2

    monkeypatch.setattr("services.shared_market_db.get_shared_vector_store", lambda: _Store())
    result = db_price_refresh.remove_delisted_from_market_library(symbols=["B", "A"])

    assert called["symbols"] == ["A", "B"]
    assert result["removed"] == 2
    assert result["symbols"] == ["A", "B"]
    assert "timestamp" in result
