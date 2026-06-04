"""Startup performance helpers (dividend sync throttle, fast portfolio load)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.portfolio_dividend_sync_service import (
    DividendSyncStats,
    maybe_sync_received_dividends,
)
from services.portfolio_ui_cache import (
    DIVIDEND_SYNC_INTERVAL,
    mark_dividend_sync_completed,
    should_sync_dividends_on_startup,
)
from services.sp500_peers_service import coverage_stats


def test_should_sync_dividends_when_no_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.portfolio_ui_cache._dividend_sync_meta_path",
        lambda: tmp_path / "dividend_sync_at.txt",
    )
    assert should_sync_dividends_on_startup() is True


def test_should_skip_dividend_sync_when_recent(tmp_path, monkeypatch):
    meta = tmp_path / "dividend_sync_at.txt"
    monkeypatch.setattr(
        "services.portfolio_ui_cache._dividend_sync_meta_path",
        lambda: meta,
    )
    mark_dividend_sync_completed()
    assert should_sync_dividends_on_startup() is False


def test_should_sync_dividends_when_timestamp_expired(tmp_path, monkeypatch):
    meta = tmp_path / "dividend_sync_at.txt"
    meta.parent.mkdir(parents=True, exist_ok=True)
    old = datetime.now() - DIVIDEND_SYNC_INTERVAL - timedelta(hours=1)
    meta.write_text(old.isoformat(), encoding="utf-8")
    monkeypatch.setattr(
        "services.portfolio_ui_cache._dividend_sync_meta_path",
        lambda: meta,
    )
    assert should_sync_dividends_on_startup() is True


def test_maybe_sync_skips_when_recent(tmp_path, monkeypatch):
    meta = tmp_path / "dividend_sync_at.txt"
    monkeypatch.setattr(
        "services.portfolio_ui_cache._dividend_sync_meta_path",
        lambda: meta,
    )
    mark_dividend_sync_completed()
    with patch(
        "services.portfolio_dividend_sync_service.sync_received_dividends"
    ) as sync:
        assert maybe_sync_received_dividends() is None
        sync.assert_not_called()


def test_maybe_sync_runs_when_forced():
    stats = DividendSyncStats(1, 0, 0, 0)
    with patch(
        "services.portfolio_dividend_sync_service.sync_received_dividends",
        return_value=stats,
    ) as sync:
        with patch(
            "services.portfolio_dividend_sync_service.mark_dividend_sync_completed"
        ):
            result = maybe_sync_received_dividends(force=True)
    assert result == stats
    sync.assert_called_once()


def test_coverage_stats_uses_count_symbols_in(monkeypatch):
    from services import sp500_peers_service

    sp500_peers_service._coverage_cache = None
    store = MagicMock()
    store.count.return_value = 100
    store.count_symbols_in.return_value = 42
    monkeypatch.setattr(sp500_peers_service, "_store", lambda: store)
    monkeypatch.setattr(
        sp500_peers_service,
        "sp500_symbol_set",
        lambda: {"AAPL", "MSFT"},
    )
    result = coverage_stats(force=True)
    assert result["analysed_sp500"] == 42
    assert result["analysed_total"] == 100
    store.get_all_documents.assert_not_called()
