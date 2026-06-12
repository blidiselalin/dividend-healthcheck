"""Tests for S&P 500 universe helpers."""
# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path

import pytest

from data_ingestion.sp500_universe import (
    _FALLBACK_SYMBOLS,
    get_sp500_symbols,
    sectors_match,
    yahoo_ticker,
)


def test_yahoo_ticker_normalizes_dots() -> None:
    assert yahoo_ticker("BRK.B") == "BRK-B"


def test_sectors_match_aliases() -> None:
    assert sectors_match("Health Care", "Healthcare")
    assert sectors_match("Consumer Defensive", "Consumer Staples")
    assert not sectors_match("Energy", "Technology")


def test_get_sp500_symbols_returns_list() -> None:
    symbols = get_sp500_symbols()
    assert len(symbols) >= 400
    assert "AAPL" in symbols
    assert "MSFT" in symbols


def test_bundled_list_not_minimal_fallback() -> None:
    symbols = get_sp500_symbols()
    assert len(symbols) > len(_FALLBACK_SYMBOLS)


def test_load_bundled_sp500_uses_repo_file_when_data_dir_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from data_ingestion import sp500_universe as mod

    monkeypatch.setattr(mod, "DEFAULT_CACHE_PATH", tmp_path / "missing" / "sp500_symbols.json")
    bundled = mod._load_bundled_sp500()
    assert bundled is not None
    assert len(bundled) >= 400
