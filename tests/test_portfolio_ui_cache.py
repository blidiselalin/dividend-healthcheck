"""Portfolio UI cache staleness after market library updates."""

from __future__ import annotations

from datetime import datetime, timedelta

from services.portfolio_ui_cache import cache_is_stale


def test_cache_is_stale_when_older_than_max_age():
    bundle = {
        "saved_at": (datetime.now() - timedelta(hours=48)).isoformat(),
        "rows": [{"symbol": "KO"}],
    }
    assert cache_is_stale(bundle) is True


def test_cache_is_stale_when_library_is_newer(monkeypatch):
    saved = datetime.now() - timedelta(days=6)
    bundle = {"saved_at": saved.isoformat(), "rows": [{"symbol": "KO"}]}
    monkeypatch.setattr(
        "services.portfolio_ui_cache.market_library_latest_update",
        lambda: datetime.now(),
    )
    assert cache_is_stale(bundle) is True


def test_cache_is_fresh_when_recent_and_library_unchanged(monkeypatch):
    saved = datetime.now() - timedelta(hours=1)
    bundle = {"saved_at": saved.isoformat(), "rows": [{"symbol": "KO"}]}
    monkeypatch.setattr(
        "services.portfolio_ui_cache.market_library_latest_update",
        lambda: saved,
    )
    assert cache_is_stale(bundle) is False
