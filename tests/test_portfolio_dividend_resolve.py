"""Tests for multi-source portfolio dividend resolution."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from data_ingestion.models import DividendRecord, StockDocument
from models.stock import StockData
from services.portfolio_dividend_resolve import (
    EXPOSED_SOURCES,
    PortfolioDividendStatus,
    load_resolved_portfolio_documents,
    resolve_dividend_document,
)


def test_resolve_uses_library_history_without_yahoo() -> None:
    document = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(ex_date=date(2025, 11, 15), payment_date=date(2025, 12, 1), amount=0.48),
            DividendRecord(ex_date=date(2025, 8, 15), payment_date=date(2025, 9, 1), amount=0.47),
            DividendRecord(ex_date=date(2025, 5, 15), payment_date=date(2025, 6, 1), amount=0.46),
            DividendRecord(ex_date=date(2025, 2, 14), payment_date=date(2025, 3, 1), amount=0.45),
        ],
    )

    with patch(
        "services.portfolio_dividend_resolve.enrich_document_payment_dates",
        side_effect=lambda _sym, doc, fetch_nasdaq=False: doc,
    ):
        resolved, status = resolve_dividend_document("KO", document, fetch_remote=False)

    assert resolved is not None
    assert len(resolved.dividend_history or []) == 4
    assert status.has_dividend_history
    assert "market library" in status.sources_found
    assert status.missing_message is None


def test_resolve_merges_yahoo_when_library_is_thin() -> None:
    document = StockDocument(
        symbol="XYZ",
        name="Example",
        dividend_history=[
            DividendRecord(ex_date=date(2025, 11, 15), payment_date=None, amount=0.25),
        ],
    )
    yahoo_records = [
        DividendRecord(ex_date=date(2025, 8, 15), payment_date=None, amount=0.24),
        DividendRecord(ex_date=date(2025, 5, 15), payment_date=None, amount=0.23),
        DividendRecord(ex_date=date(2025, 2, 14), payment_date=None, amount=0.22),
    ]

    with (
        patch(
            "services.portfolio_dividend_resolve._records_from_yfinance",
            return_value=yahoo_records,
        ) as yahoo_fetch,
        patch(
            "services.portfolio_dividend_resolve.enrich_document_payment_dates",
            side_effect=lambda _sym, doc, fetch_nasdaq=False: doc,
        ),
    ):
        resolved, status = resolve_dividend_document("XYZ", document, fetch_remote=True)

    yahoo_fetch.assert_called_once()
    assert resolved is not None
    assert len(resolved.dividend_history or []) == 4
    assert "Yahoo Finance" in status.sources_found


def test_resolve_merges_yahoo_when_library_already_has_history() -> None:
    document = StockDocument(
        symbol="KO",
        name="Coca-Cola",
        dividend_history=[
            DividendRecord(ex_date=date(2025, 11, 15), payment_date=date(2025, 12, 1), amount=0.48),
            DividendRecord(ex_date=date(2025, 8, 15), payment_date=date(2025, 9, 1), amount=0.47),
            DividendRecord(ex_date=date(2025, 5, 15), payment_date=date(2025, 6, 1), amount=0.46),
            DividendRecord(ex_date=date(2025, 2, 14), payment_date=date(2025, 3, 1), amount=0.45),
        ],
    )
    yahoo_records = [
        DividendRecord(ex_date=date(2026, 2, 14), payment_date=None, amount=0.49),
    ]

    with (
        patch(
            "services.portfolio_dividend_resolve._records_from_yfinance",
            return_value=yahoo_records,
        ) as yahoo_fetch,
        patch(
            "services.portfolio_dividend_resolve.enrich_document_payment_dates",
            side_effect=lambda _sym, doc, fetch_nasdaq=False: doc,
        ),
    ):
        resolved, status = resolve_dividend_document("KO", document, fetch_remote=True)

    yahoo_fetch.assert_called_once()
    assert resolved is not None
    assert len(resolved.dividend_history or []) == 5
    assert resolved.dividend_history[-1].ex_date == date(2026, 2, 14)
    assert "Yahoo Finance" in status.sources_found


def test_resolve_skips_yahoo_when_remote_fetch_disabled() -> None:
    document = StockDocument(
        symbol="XYZ",
        name="Example",
        dividend_history=[
            DividendRecord(ex_date=date(2025, 11, 15), payment_date=None, amount=0.25),
        ],
    )

    with patch(
        "services.portfolio_dividend_resolve._records_from_yfinance",
        return_value=[],
    ) as yahoo_fetch:
        resolved, status = resolve_dividend_document("XYZ", document, fetch_remote=False)

    yahoo_fetch.assert_not_called()
    assert resolved is not None
    assert len(resolved.dividend_history or []) == 1
    assert "Yahoo Finance" not in status.sources_found


def test_resolve_reports_missing_when_no_history_or_metadata() -> None:
    with patch("services.portfolio_dividend_resolve._records_from_yfinance", return_value=[]):
        resolved, status = resolve_dividend_document("NODIV", None, fetch_remote=False)

    assert resolved is None
    assert not status.has_dividend_history
    assert status.missing_message is not None
    assert "No dividend history found" in status.missing_message
    for source in ("market library", "Postgres history", "Yahoo Finance"):
        assert source in status.sources_checked


def test_resolve_metadata_fallback_message() -> None:
    stock = StockData(
        symbol="META",
        name="Meta",
        sector="Tech",
        industry="Internet",
        dividend_rate=1.0,
    )

    with patch("services.portfolio_dividend_resolve._records_from_yfinance", return_value=[]):
        _resolved, status = resolve_dividend_document("META", None, stock=stock, fetch_remote=False)

    assert not status.has_dividend_history
    assert status.uses_metadata_fallback
    assert status.missing_message is not None
    assert "annual dividend estimate" in status.missing_message


def test_load_resolved_portfolio_documents_batch() -> None:
    docs = {
        "KO": StockDocument(
            symbol="KO",
            name="Coca-Cola",
            dividend_history=[
                DividendRecord(ex_date=date(2025, 11, 15), payment_date=None, amount=0.48),
            ],
        )
    }

    with patch(
        "services.portfolio_dividend_resolve.resolve_dividend_document",
        side_effect=lambda symbol, document, **kwargs: (
            document,
            PortfolioDividendStatus(
                symbol=symbol,
                history_count=len(document.dividend_history or []) if document else 0,
                sources_checked=EXPOSED_SOURCES[:3],
                sources_found=("market library",),
                payment_date_sources=(),
            ),
        ),
    ):
        resolved, statuses = load_resolved_portfolio_documents(["KO"], documents=docs)

    assert "KO" in resolved
    assert statuses["KO"].has_dividend_history


def test_load_resolved_always_fetches_library_and_prefers_it_over_empty_seed() -> None:
    seed = {
        "KO": StockDocument(symbol="KO", name="KO", dividend_history=[]),
    }
    library = {
        "KO": StockDocument(
            symbol="KO",
            name="Coca-Cola",
            dividend_history=[
                DividendRecord(ex_date=date(2025, 11, 15), payment_date=None, amount=0.48),
            ],
        )
    }

    with (
        patch("services.shared_market_db.load_documents", return_value=library) as load_mock,
        patch(
            "services.portfolio_dividend_resolve.enrich_document_payment_dates",
            side_effect=lambda _sym, doc, fetch_nasdaq=False: doc,
        ),
    ):
        resolved, statuses = load_resolved_portfolio_documents(["KO"], documents=seed)

    load_mock.assert_called_once_with(["KO"])
    assert resolved["KO"] is not None
    assert len(resolved["KO"].dividend_history or []) == 1
    assert statuses["KO"].has_dividend_history


def test_attach_postgres_history_builds_document_from_tables() -> None:
    from services.portfolio_dividend_resolve import _attach_postgres_history

    table_rows = [
        DividendRecord(ex_date=date(2025, 11, 15), payment_date=date(2025, 12, 1), amount=0.48),
    ]

    with (
        patch("db.connection.use_cloud_sql", return_value=True),
        patch(
            "db.postgres_market_history_store.PostgresMarketHistoryStore.load_dividend_history",
            return_value=table_rows,
        ),
    ):
        doc = _attach_postgres_history(None, symbol="KO")

    assert doc is not None
    assert doc.symbol == "KO"
    assert len(doc.dividend_history or []) == 1
