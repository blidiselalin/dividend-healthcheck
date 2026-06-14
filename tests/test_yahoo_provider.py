"""Tests for Yahoo provider transformations without live network."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from data_ingestion.providers.yahoo import YahooFinanceProvider


class _FakeTicker:
    def __init__(self) -> None:
        self.info = {
            "longName": "Coca-Cola Co",
            "sector": "Consumer Defensive",
            "industry": "Beverages",
            "exchange": "NYSE",
            "dividendYield": 0.031,
            "dividendRate": 1.94,
            "payoutRatio": 0.66,
            "trailingPE": 22.5,
            "forwardPE": 20.5,
            "regularMarketPrice": 61.0,
            "currentPrice": 61.2,
            "marketCap": 260_000_000_000,
            "fiftyTwoWeekHigh": 66.0,
            "fiftyTwoWeekLow": 55.0,
            "targetMeanPrice": 64.0,
            "numberOfAnalystOpinions": 24,
            "recommendationKey": "buy",
            "trailingEps": 2.5,
            "freeCashflow": 10_000_000_000,
            "sharesOutstanding": 4_300_000_000,
            "exDividendDate": 1713225600,  # 2024-04-16 UTC
        }
        self.fast_info = SimpleNamespace(last_price=60.0, market_cap=123, year_high=70.0, year_low=50.0)

    def history(self, period: str, auto_adjust: bool):
        assert period == "10y"
        assert auto_adjust is True
        return pd.DataFrame(
            {
                "Open": [60.0, 61.0],
                "High": [62.0, 63.0],
                "Low": [59.0, 60.0],
                "Close": [61.0, 62.0],
                "Volume": [1_000_000, 1_100_000],
            },
            index=[datetime(2024, 1, 2), datetime(2024, 1, 3)],
        )

    @property
    def dividends(self):
        return pd.Series([0.48, 0.50], index=[datetime(2024, 3, 15), datetime(2024, 6, 14)])


class _FallbackTicker:
    @property
    def info(self):
        raise RuntimeError("no full info")

    @property
    def fast_info(self):
        return SimpleNamespace(last_price=44.5, market_cap=111, year_high=49.0, year_low=40.0)


def test_yahoo_provider_fetch_maps_snapshot(monkeypatch) -> None:
    monkeypatch.setattr("data_ingestion.providers.yahoo.YFINANCE_AVAILABLE", True)
    monkeypatch.setattr(
        "data_ingestion.providers.yahoo.yf",
        SimpleNamespace(Ticker=lambda symbol: _FakeTicker()),
    )

    provider = YahooFinanceProvider(request_delay=0)
    snapshot = provider.fetch("ko")

    assert snapshot is not None
    assert snapshot.symbol == "KO"
    assert snapshot.name == "Coca-Cola Co"
    assert snapshot.dividend_yield == 3.1
    assert snapshot.current_price == 61.2
    assert snapshot.analyst_rating == "buy"
    assert snapshot.num_analysts == 24
    assert len(snapshot.price_history) == 2
    assert len(snapshot.dividend_history) == 2


def test_yahoo_provider_info_falls_back_to_fast_info() -> None:
    info = YahooFinanceProvider._info(_FallbackTicker())
    assert info is not None
    assert info["currentPrice"] == 44.5
    assert info["fiftyTwoWeekHigh"] == 49.0


def test_yahoo_provider_returns_none_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("data_ingestion.providers.yahoo.YFINANCE_AVAILABLE", False)
    provider = YahooFinanceProvider(request_delay=0)
    assert provider.fetch("KO") is None
