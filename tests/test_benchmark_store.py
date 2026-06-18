"""
Unit tests for db.benchmark_store.BenchmarkPriceStore.

All tests run in SQLite mode (PYTEST_USE_SQLITE=1 set by conftest autouse fixture).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from db.benchmark_store import BENCHMARK_ETF_SEED, BenchmarkPriceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store(tmp_path: Path) -> BenchmarkPriceStore:
    return BenchmarkPriceStore(db_path=tmp_path / "benchmark.db")


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------


class TestUpsertAndLoadPrices:
    def test_round_trip_single_symbol(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        prices = {
            date(2024, 1, 31): 4850.50,
            date(2024, 2, 29): 5100.25,
            date(2024, 3, 28): 5248.10,
        }
        written = store.upsert_prices("^GSPC", prices)
        assert written == 3

        loaded = store.load_prices("^GSPC", date(2024, 1, 1), date(2024, 3, 31))
        assert len(loaded) == 3
        assert abs(loaded[date(2024, 1, 31)] - 4850.50) < 0.01

    def test_symbol_case_insensitive(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_prices("schd", {date(2024, 5, 31): 82.55})
        loaded = store.load_prices("SCHD", date(2024, 1, 1), date(2024, 12, 31))
        assert date(2024, 5, 31) in loaded

    def test_date_range_filter(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_prices(
            "SCHD",
            {
                date(2023, 12, 29): 75.00,
                date(2024, 1, 31): 76.50,
                date(2024, 2, 29): 78.00,
            },
        )
        loaded = store.load_prices("SCHD", date(2024, 1, 1), date(2024, 1, 31))
        assert date(2024, 1, 31) in loaded
        assert date(2023, 12, 29) not in loaded

    def test_upsert_updates_existing_price(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_prices("SPY", {date(2024, 6, 28): 550.00})
        store.upsert_prices("SPY", {date(2024, 6, 28): 551.50})
        loaded = store.load_prices("SPY", date(2024, 1, 1), date(2024, 12, 31))
        assert abs(loaded[date(2024, 6, 28)] - 551.50) < 0.01

    def test_empty_prices_returns_zero(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.upsert_prices("SPY", {}) == 0

    def test_load_returns_empty_for_unknown_symbol(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        loaded = store.load_prices("UNKNOWN", date(2024, 1, 1), date(2024, 12, 31))
        assert loaded == {}


class TestCoveredSymbolsAndLatestDate:
    def test_covered_symbols(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.covered_symbols() == set()
        store.upsert_prices("^GSPC", {date(2024, 1, 31): 4900.0})
        store.upsert_prices("SCHD", {date(2024, 1, 31): 77.0})
        assert store.covered_symbols() == {"^GSPC", "SCHD"}

    def test_latest_date_none_when_empty(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.latest_date("^GSPC") is None

    def test_latest_date_after_multiple_rows(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_prices(
            "^GSPC",
            {
                date(2024, 1, 31): 4850.0,
                date(2024, 3, 28): 5100.0,
                date(2024, 2, 29): 5000.0,
            },
        )
        assert store.latest_date("^GSPC") == date(2024, 3, 28)

    def test_price_count(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.price_count("^GSPC") == 0
        store.upsert_prices("^GSPC", {date(2024, 1, 31): 100.0, date(2024, 2, 29): 101.0})
        assert store.price_count("^GSPC") == 2


# ---------------------------------------------------------------------------
# ETF metadata / best practices
# ---------------------------------------------------------------------------


class TestEtfMetadata:
    def test_get_etf_info_returns_none_when_missing(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.get_etf_info("SCHD") is None

    def test_upsert_and_get_etf_info(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_etf_info(
            "SCHD",
            display_name="SCHD",
            full_name="Schwab U.S. Dividend Equity ETF",
            description="Dividend quality screen.",
            expense_ratio_pct=0.06,
            category="US Large Cap Dividend",
            currency="USD",
            best_practices="Hold long-term.",
        )
        info = store.get_etf_info("SCHD")
        assert info is not None
        assert info["display_name"] == "SCHD"
        assert abs(info["expense_ratio_pct"] - 0.06) < 1e-9
        assert info["best_practices"] == "Hold long-term."

    def test_upsert_etf_info_case_insensitive(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_etf_info(
            "schd",
            display_name="SCHD",
            full_name="Schwab U.S. Dividend Equity ETF",
        )
        assert store.get_etf_info("SCHD") is not None

    def test_upsert_overwrites_existing(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_etf_info("SCHD", display_name="Old", full_name="Old full")
        store.upsert_etf_info("SCHD", display_name="New", full_name="New full")
        info = store.get_etf_info("SCHD")
        assert info is not None
        assert info["display_name"] == "New"

    def test_get_all_etf_info_empty(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        assert store.get_all_etf_info() == {}

    def test_get_all_etf_info_returns_all(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_etf_info("^GSPC", display_name="S&P 500", full_name="S&P 500 Index")
        store.upsert_etf_info("SCHD", display_name="SCHD", full_name="Schwab Dividend ETF")
        all_info = store.get_all_etf_info()
        assert "^GSPC" in all_info
        assert "SCHD" in all_info


class TestSeedEtfInfo:
    def test_seed_populates_all_symbols(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        written = store.seed_etf_info_if_empty()
        assert written == len(BENCHMARK_ETF_SEED)
        for sym in BENCHMARK_ETF_SEED:
            info = store.get_etf_info(sym)
            assert info is not None
            assert info["display_name"]
            assert info["best_practices"]

    def test_seed_is_idempotent(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.seed_etf_info_if_empty()
        written_second = store.seed_etf_info_if_empty()
        assert written_second == 0

    def test_seed_skips_already_present(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_etf_info("^GSPC", display_name="Custom", full_name="Custom full")
        store.seed_etf_info_if_empty()
        # Custom row must not be overwritten by seed
        info = store.get_etf_info("^GSPC")
        assert info is not None
        assert info["display_name"] == "Custom"
