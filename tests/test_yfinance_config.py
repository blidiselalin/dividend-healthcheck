"""Tests for yfinance cache configuration and log filtering."""
# ruff: noqa: S101

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from utils.yfinance_config import YfinanceNoiseFilter, configure_yfinance


def test_yfinance_noise_filter_drops_tzcache_and_delisted() -> None:
    filt = YfinanceNoiseFilter()
    tz = logging.LogRecord(
        "yfinance", logging.INFO, "", 0, "Failed to create TzCache folder", (), None
    )
    delisted = logging.LogRecord(
        "yfinance",
        logging.ERROR,
        "",
        0,
        "$BK: possibly delisted; no price data found  (period=5d)",
        (),
        None,
    )
    normal = logging.LogRecord("yfinance", logging.INFO, "", 0, "Fetched quote for KO", (), None)

    assert filt.filter(tz) is False
    assert filt.filter(delisted) is False
    assert filt.filter(normal) is True


def test_configure_yfinance_uses_data_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import utils.yfinance_config as mod

    monkeypatch.setattr(mod, "yfinance_cache_dir", lambda: tmp_path / "cache" / "yfinance")
    mod._CONFIGURED = False
    configure_yfinance()
    cache_dir = mod.yfinance_cache_dir()
    assert cache_dir.is_dir()
