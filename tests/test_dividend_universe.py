"""Tests for top dividend universe helpers."""
# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path

import pytest

from data_ingestion.dividend_universe import (
    build_top_dividend_symbols,
    get_top_dividend_symbols,
    load_cached_symbols,
)


def test_get_top_dividend_symbols_returns_about_one_hundred() -> None:
    symbols = get_top_dividend_symbols()
    assert len(symbols) >= 90
    assert len(symbols) <= 100
    assert "KO" in symbols
    assert "JNJ" in symbols
    assert "ABBV" in symbols


def test_build_top_dividend_symbols_filters_to_sp500(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "data_ingestion.dividend_universe.fetch_aristocrats_from_wikipedia",
        lambda: ["KO", "PEP", "ABBV"],
    )
    symbols = build_top_dividend_symbols(sp500={"KO", "PEP", "FAKE"}, limit=2)
    assert symbols == ["KO", "PEP"]


def test_load_bundled_top_dividend_json() -> None:
    repo = Path(__file__).resolve().parent.parent / "data" / "top_dividend_symbols.json"
    symbols = load_cached_symbols(repo, enforce_ttl=False)
    assert symbols is not None
    assert len(symbols) == 100


def test_config_all_dividend_stocks_matches_bundle() -> None:
    from config import ALL_DIVIDEND_STOCKS, TOP_DIVIDEND_STOCKS  # type: ignore[attr-defined]

    assert len(TOP_DIVIDEND_STOCKS) == 100
    assert ALL_DIVIDEND_STOCKS == TOP_DIVIDEND_STOCKS
