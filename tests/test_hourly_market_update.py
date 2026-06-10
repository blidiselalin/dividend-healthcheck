"""Tests for scheduled hourly market refresh helpers."""

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

_root = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "hourly_market_update",
    _root / "services" / "hourly_market_update.py",
)
_hourly = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_hourly)
enrich_stale_documents = _hourly.enrich_stale_documents


def _doc(
    symbol: str,
    *,
    days_old: int = 10,
    quality: float = 40.0,
    price_points: int = 0,
    div_points: int = 0,
):
    from datetime import date

    from data_ingestion.models import DividendRecord, PriceHistory

    doc = MagicMock()
    doc.symbol = symbol
    doc.last_updated = datetime.now() - timedelta(days=days_old)
    doc.data_quality = quality
    doc.price_history = [
        PriceHistory(
            date=date(2020, 1, 1) + timedelta(days=i),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1,
        )
        for i in range(price_points)
    ]
    doc.dividend_history = [
        DividendRecord(
            ex_date=date(2020, 1, 1) + timedelta(days=i * 90),
            payment_date=None,
            amount=1.0,
        )
        for i in range(div_points)
    ]
    return doc


@patch("data_ingestion.stock_enricher.create_stock_enricher")
@patch("services.shared_market_db.get_shared_vector_store")
def test_enrich_stale_documents_limits_batch(mock_get_store, mock_create_enricher):
    store = mock_get_store.return_value
    store.get_all_documents.return_value = [
        _doc("AAA", days_old=30),
        _doc("BBB", days_old=20),
        _doc("CCC", days_old=15),
        _doc("FRESH", days_old=1, quality=90.0, price_points=300, div_points=4),
    ]

    enriched_doc = MagicMock()
    enricher = mock_create_enricher.return_value
    enricher.enrich_document.side_effect = lambda d: enriched_doc

    stats = enrich_stale_documents(stale_days=7, limit=2)

    assert stats["candidates"] == 3
    assert stats["enriched"] == 2
    assert len(stats["symbols"]) == 2
    assert enricher.enrich_document.call_count == 2
    store.add_documents.assert_called_once()


@patch("services.sp500_peers_service.ensure_sp500_in_vectordb")
@patch("services.db_price_refresh.refresh_market_library_prices")
def test_run_hourly_market_update_orchestration(mock_prices, mock_sp500):
    mock_prices.return_value = {"updated": 12, "total": 20}
    mock_sp500.return_value = {"created": 1, "errors": 0}

    with patch.object(_hourly, "enrich_stale_documents") as mock_enrich:
        mock_enrich.return_value = {"enriched": 3, "candidates": 10}
        summary = _hourly.run_hourly_market_update(
            stale_days=5,
            enrich_limit=15,
            sp500_new_limit=2,
        )

    mock_prices.assert_called_once()
    mock_sp500.assert_called_once_with(limit=2)
    mock_enrich.assert_called_once_with(stale_days=5, limit=15)
    assert summary["prices"]["updated"] == 12
    assert summary["sp500"]["created"] == 1
    assert summary["enrich"]["enriched"] == 3
    assert "elapsed_seconds" in summary


@patch("services.hourly_market_update.run_hourly_market_update")
def test_ingest_data_hourly_update_cli(mock_run, capsys):
    mock_run.return_value = {
        "prices": {"updated": 5, "total": 10},
        "sp500": {"created": 0},
        "enrich": {"enriched": 2, "candidates": 8},
        "elapsed_seconds": 4.5,
    }

    from ingest_data import main

    with patch("sys.argv", ["ingest_data.py", "--hourly-update", "--hourly-enrich-limit", "25"]):
        assert main() == 0

    mock_run.assert_called_once_with(stale_days=7, enrich_limit=25)
    assert "Hourly update complete" in capsys.readouterr().out


@patch("services.sp500_peers_service.ensure_top_dividend_in_vectordb")
def test_ingest_data_ensure_top_dividend_cli(mock_ensure, capsys):
    mock_ensure.return_value = {"created": 3, "errors": 0, "already_present": 97}

    from ingest_data import main

    with patch(
        "sys.argv",
        ["ingest_data.py", "--ensure-top-dividend", "--top-dividend-limit", "10"],
    ):
        assert main() == 0

    mock_ensure.assert_called_once()
    assert mock_ensure.call_args.kwargs["limit"] == 10
    assert "Top dividend ingest complete" in capsys.readouterr().out


@patch("services.db_price_refresh.remove_delisted_from_market_library")
def test_ingest_data_remove_delisted_cli(mock_remove, capsys):
    mock_remove.return_value = {"removed": 2, "symbols": ["WBA", "ZZ"]}

    from ingest_data import main

    with patch("sys.argv", ["ingest_data.py", "--remove-delisted"]):
        assert main() == 0

    mock_remove.assert_called_once()
    assert "Delisted symbols removed" in capsys.readouterr().out
