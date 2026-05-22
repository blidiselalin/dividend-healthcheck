"""Tests for live market price overlay on vector-DB snapshots."""

from unittest.mock import MagicMock, patch

from models.stock import StockData
from services.live_price import apply_live_price, fetch_latest_market_price


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
def test_apply_live_price_overrides_stale_snapshot(mock_fetch):
    data = _stock(price=393.0)

    result = apply_live_price(data)

    mock_fetch.assert_called_once_with("INTU")
    assert result.price == 307.07
    assert "Price: Live" in (result.data_sources or [])


@patch("services.live_price.fetch_latest_market_price", return_value=None)
def test_apply_live_price_keeps_cached_when_fetch_fails(mock_fetch):
    data = _stock(price=393.0)

    result = apply_live_price(data)

    assert result.price == 393.0
    assert "Price: Live" not in (result.data_sources or [])


@patch("yfinance.Ticker")
def test_fetch_latest_market_price_reads_fast_info(mock_ticker_cls):
    fast_info = MagicMock()
    fast_info.get.side_effect = lambda key: 307.07 if key == "lastPrice" else None
    mock_ticker_cls.return_value.fast_info = fast_info

    assert fetch_latest_market_price("INTU") == 307.07


@patch("services.live_price.apply_live_price")
@patch("services.portfolio_details_service._fetch_statistics_stock")
@patch("services.portfolio_details_service.PortfolioDetailsService._load_documents")
def test_get_stock_data_applies_live_price(mock_docs, mock_stats, mock_apply):
    from services.portfolio_details_service import get_stock_data

    stale = _stock(price=393.0)
    mock_docs.return_value = {"INTU": MagicMock()}
    mock_stats.return_value = stale
    mock_apply.side_effect = lambda data: setattr(data, "price", 307.07) or data

    data = get_stock_data("INTU")

    mock_apply.assert_called_once_with(stale)
    assert data.price == 307.07
