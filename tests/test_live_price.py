"""Tests for live market price overlay on vector-DB snapshots."""
# ruff: noqa: S101

from typing import Any
from unittest.mock import MagicMock, patch

from models.stock import StockData
from services.live_price import (
    apply_live_price,
    fetch_latest_market_price,
    fetch_previous_close,
)


def _stock(*, price: float = 393.0) -> StockData:
    return StockData(
        symbol="INTU",
        name="Intuit Inc.",
        sector="Technology",
        industry="Software",
        price=price,
        dividend_yield_pct=0.8,
    )


@patch("services.live_price.fetch_latest_market_price", return_value=307.07)
def test_apply_live_price_overrides_stale_snapshot(mock_fetch: Any) -> None:
    data = _stock(price=393.0)

    result = apply_live_price(data)

    mock_fetch.assert_called_once_with("INTU")
    assert result.price == 307.07
    assert "Price: Live" in (result.data_sources or [])


@patch("services.live_price.fetch_latest_market_price", return_value=None)
def test_apply_live_price_keeps_cached_when_fetch_fails(mock_fetch: Any) -> None:
    data = _stock(price=393.0)

    result = apply_live_price(data)

    assert result.price == 393.0
    assert "Price: Live" not in (result.data_sources or [])


def test_fetch_previous_close_rejects_empty_symbol() -> None:
    assert fetch_previous_close("") is None
    assert fetch_previous_close("   ") is None


@patch("yfinance.Ticker")
def test_fetch_previous_close_reads_fast_info(mock_ticker_cls: Any) -> None:
    fast_info = MagicMock()
    fast_info.get.side_effect = lambda key: 645.0 if key == "previousClose" else None
    mock_ticker_cls.return_value.fast_info = fast_info

    assert fetch_previous_close("INTU") == 645.0


@patch("yfinance.Ticker")
def test_fetch_previous_close_falls_back_to_history(mock_ticker_cls: Any) -> None:
    import pandas as pd

    mock_ticker_cls.return_value.fast_info = None
    mock_ticker_cls.return_value.history.return_value = pd.DataFrame(
        {"Close": [640.0, 645.0, 650.0]}
    )

    assert fetch_previous_close("INTU") == 645.0


@patch("yfinance.Ticker")
def test_fetch_latest_market_price_reads_fast_info(mock_ticker_cls: Any) -> None:
    fast_info = MagicMock()
    fast_info.get.side_effect = lambda key: 307.07 if key == "lastPrice" else None
    mock_ticker_cls.return_value.fast_info = fast_info

    assert fetch_latest_market_price("INTU") == 307.07


@patch("services.stock_analysis_service.load_independent_stock_analysis")
def test_load_stock_data_delegates_to_independent_analysis(mock_load: Any) -> None:
    from services.stock_analysis_service import (
        IndependentStockAnalysis,
        load_stock_data,
    )

    stale = _stock(price=307.07)
    mock_load.return_value = IndependentStockAnalysis(
        symbol="INTU",
        stock_data=stale,
        document=None,
        yield_channel=None,
        price_history_points=200,
        dividend_history_points=4,
        dividend_yield_source="history",
        history_summary={"library_hit": True},
    )

    data = load_stock_data("INTU")

    mock_load.assert_called_once()
    assert mock_load.call_args.args[0] == "INTU"
    assert data is stale
    assert data.price == 307.07
