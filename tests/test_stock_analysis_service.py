"""Tests for independent stock analysis service."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from data_ingestion.models import DividendRecord, PriceHistory, StockDocument


def _library_doc(*, chart_ready: bool = False) -> StockDocument:
    doc = StockDocument(symbol="INTU", name="Intuit", sector="Technology")
    doc.dividend_yield = None
    if chart_ready:
        doc.price_history = [
            PriceHistory(
                date=date(2020, 1, 1) + timedelta(days=i),
                open=650.0,
                high=660.0,
                low=640.0,
                close=650.0 + i * 0.01,
                volume=900_000,
            )
            for i in range(260)
        ]
    else:
        doc.price_history = [
            PriceHistory(
                date=date(2024, 6, 1),
                open=650.0,
                high=660.0,
                low=640.0,
                close=650.0,
                volume=900_000,
            )
        ] * 200
    doc.dividend_history = [
        DividendRecord(ex_date=date(2024, m, 1), payment_date=date(2024, m, 15), amount=1.1)
        for m in (2, 5, 8, 11)
    ]
    return doc


def test_ensure_yield_channel_data_skips_backfill_by_default() -> None:
    from services.stock_analysis_service import ensure_yield_channel_data

    doc = _library_doc()
    mock_channel = MagicMock()

    with (
        patch(
            "services.stock_analysis_service.load_yield_channel_data",
            return_value=mock_channel,
        ) as mock_load,
        patch("services.stock_history_backfill.backfill_thin_history") as mock_backfill,
    ):
        result = ensure_yield_channel_data("INTU", document=doc)

    assert result is mock_channel
    mock_backfill.assert_not_called()
    mock_load.assert_called_once()
    assert mock_load.call_args.kwargs.get("library_only") is True


def test_ensure_yield_channel_data_skips_backfill_when_channel_exists() -> None:
    from services.stock_analysis_service import ensure_yield_channel_data

    doc = _library_doc()
    mock_channel = MagicMock()

    with (
        patch(
            "services.stock_analysis_service.load_yield_channel_data",
            return_value=mock_channel,
        ),
        patch("services.stock_history_backfill.backfill_thin_history") as mock_backfill,
    ):
        result = ensure_yield_channel_data("INTU", document=doc, allow_backfill=True)

    assert result is mock_channel
    mock_backfill.assert_not_called()


def test_ensure_yield_channel_data_backfills_thin_history() -> None:
    from services.stock_analysis_service import ensure_yield_channel_data

    doc = _library_doc()
    mock_channel = MagicMock()

    with (
        patch(
            "services.stock_analysis_service.load_yield_channel_data",
            side_effect=[None, mock_channel],
        ),
        patch("services.shared_market_db.get_document", return_value=doc),
        patch("services.stock_history_backfill.backfill_thin_history") as mock_backfill,
    ):
        result = ensure_yield_channel_data("INTU", document=doc, allow_backfill=True)

    mock_backfill.assert_called_once_with(
        symbols=["INTU"],
        limit=1,
        prioritize_portfolio=True,
    )
    assert result is mock_channel


def test_stock_data_from_document_uses_history() -> None:
    from services.stock_analysis_service import stock_data_from_document

    doc = _library_doc()
    with patch("services.live_price.apply_live_price", side_effect=lambda s: s):
        stock = stock_data_from_document(doc, apply_live_price=True)

    assert stock.dividend_rate == 4.4
    assert stock.dividend_yield_pct is not None
    assert stock.dividend_yield_pct > 0


def test_load_independent_stock_analysis_from_library() -> None:
    from services.stock_analysis_service import load_independent_stock_analysis

    doc = _library_doc()
    mock_channel = MagicMock(current_yield=0.68)

    with (
        patch("services.live_price.apply_live_price", side_effect=lambda s: s),
        patch(
            "services.stock_analysis_service.ensure_yield_channel_data",
            return_value=mock_channel,
        ),
    ):
        analysis = load_independent_stock_analysis("INTU", document=doc)

    assert analysis is not None
    assert analysis.document is doc
    assert analysis.price_history_points == 200
    assert analysis.dividend_history_points == 4
    assert analysis.yield_channel is mock_channel


def test_load_yield_channel_data_skips_when_not_chart_ready() -> None:
    from services.stock_analysis_service import load_yield_channel_data

    doc = _library_doc()

    with (
        patch("services.shared_market_db.get_document", return_value=None),
        patch(
            "services.yield_channel_chart._default_yield_channel_service"
        ) as mock_service_factory,
    ):
        result = load_yield_channel_data("INTU", document=doc)

    assert result is None
    mock_service_factory.assert_not_called()


def test_load_yield_channel_data_passes_library_document() -> None:
    from services.stock_analysis_service import load_yield_channel_data

    doc = _library_doc(chart_ready=True)
    mock_channel = MagicMock()

    with (
        patch(
            "services.yield_channel_chart._default_yield_channel_service"
        ) as mock_service_factory,
        patch("services.shared_market_db.get_document", return_value=None),
    ):
        service = MagicMock()
        service.fetch_yield_channel_data.return_value = mock_channel
        mock_service_factory.return_value = service

        result = load_yield_channel_data("INTU", document=doc)

    assert result is mock_channel
    service.fetch_yield_channel_data.assert_called()
    first_call = service.fetch_yield_channel_data.call_args_list[0]
    assert first_call.kwargs["document"] is doc
    assert first_call.kwargs.get("library_only") is True


def test_postgres_document_from_row_merges_indexed_columns() -> None:
    from db.postgres_market_store import _document_from_row

    row = {
        "symbol": "INTU",
        "document": {
            "symbol": "INTU",
            "name": "Intuit",
            "sector": "Unknown",
            "price_history": [],
            "dividend_history": [],
        },
        "sector": "Technology",
        "dividend_streak_years": 5,
        "dividend_yield": 0.65,
        "data_quality": 88.0,
        "last_updated": "2024-06-01T12:00:00+00:00",
        "source": "yahoo",
    }
    doc = _document_from_row(row)

    assert doc.sector == "Technology"
    assert doc.dividend_yield == 0.65
    assert doc.dividend_streak_years == 5
    assert doc.data_quality == 88.0
