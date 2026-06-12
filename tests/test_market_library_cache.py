"""Tests for shared admin market-library cache helpers."""
# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_cached_thin_history_summary_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.stock_history_backfill.thin_history_summary",
        lambda: {"total": 10, "yield_ready": 8, "thin_history": 2},
    )
    with patch("ui.market_library_cache.st.cache_data", lambda **kwargs: lambda fn: fn):
        from ui.market_library_cache import cached_thin_history_summary

        result = cached_thin_history_summary()
    assert result == {"total": 10, "yield_ready": 8, "thin_history": 2}


def test_clear_thin_history_summary_cache() -> None:
    with patch("ui.market_library_cache.st.cache_data", lambda **kwargs: lambda fn: fn):
        from ui import market_library_cache

        market_library_cache.cached_thin_history_summary = MagicMock()
        market_library_cache.clear_thin_history_summary_cache()
        market_library_cache.cached_thin_history_summary.clear.assert_called_once()
