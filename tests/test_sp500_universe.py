"""Tests for S&P 500 universe helpers."""

from __future__ import annotations

from data_ingestion.sp500_universe import (
    sectors_match,
    yahoo_ticker,
    _FALLBACK_SYMBOLS,
    get_sp500_symbols,
)


def test_yahoo_ticker_normalizes_dots():
    assert yahoo_ticker("BRK.B") == "BRK-B"


def test_sectors_match_aliases():
    assert sectors_match("Health Care", "Healthcare")
    assert sectors_match("Consumer Defensive", "Consumer Staples")
    assert not sectors_match("Energy", "Technology")


def test_get_sp500_symbols_returns_list():
    symbols = get_sp500_symbols()
    assert len(symbols) >= 400
    assert "AAPL" in symbols
    assert "MSFT" in symbols


def test_bundled_list_not_minimal_fallback():
    symbols = get_sp500_symbols()
    assert len(symbols) > len(_FALLBACK_SYMBOLS)


def test_load_bundled_sp500_uses_repo_file_when_data_dir_empty(tmp_path, monkeypatch):
    from data_ingestion import sp500_universe as mod

    monkeypatch.setattr(mod, "DEFAULT_CACHE_PATH", tmp_path / "missing" / "sp500_symbols.json")
    bundled = mod._load_bundled_sp500()
    assert bundled is not None
    assert len(bundled) >= 400
