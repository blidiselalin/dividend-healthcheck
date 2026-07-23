"""Tests for portfolio details row building."""
# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import patch

from data_ingestion.portfolio_store import PortfolioStore
from models.stock import StockData
from services.portfolio_analysis_preload import PortfolioAnalysisPreload
from services.portfolio_details_service import (
    PortfolioDetailsService,
    PriceSnapshot,
)


def _stats() -> StockData:
    return StockData(
        symbol="KO",
        name="Coca-Cola Co",
        sector="Consumer",
        industry="Beverages",
        price=62.0,
        dividend_yield_pct=3.0,
    )


def _empty_snapshot() -> PriceSnapshot:
    return PriceSnapshot(
        medium_price_365d=None,
        price_180d=None,
        price_365d=None,
        change_180d_pct=None,
        change_365d_pct=None,
    )


def test_build_rows_without_live_prices_has_no_previous_close_without_history(
    portfolio_store: PortfolioStore,
) -> None:
    portfolio_store.upsert_holding(
        "KO",
        shares=10,
        avg_cost_per_share=50.0,
        company_name="Coca-Cola Co",
    )
    service = PortfolioDetailsService(store=portfolio_store)

    with (
        patch.object(service, "_load_documents", return_value=({}, {})),
        patch(
            "services.portfolio_details_service.load_portfolio_statistics_stock",
            return_value=_stats(),
        ),
        patch.object(service, "_get_price_snapshot", return_value=_empty_snapshot()),
        patch.object(service, "_get_market_extras", return_value=(None, None, None)),
    ):
        rows, _ = service.build_rows_with_cache(
            use_live_prices=False,
            preload_analysis=False,
        )

    assert len(rows) == 1
    assert rows[0].previous_close is None
    assert rows[0].current_price == 62.0


def test_build_rows_without_live_prices_uses_history_previous_close(
    portfolio_store: PortfolioStore,
) -> None:
    from datetime import date

    from data_ingestion.models import PriceHistory, StockDocument

    portfolio_store.upsert_holding(
        "KO",
        shares=10,
        avg_cost_per_share=50.0,
        company_name="Coca-Cola Co",
    )
    service = PortfolioDetailsService(store=portfolio_store)
    document = StockDocument(
        symbol="KO",
        name="Coca-Cola Co",
        current_price=62.5,
        price_history=[
            PriceHistory(
                date=date(2026, 5, 18),
                open=61.0,
                high=62.0,
                low=60.5,
                close=61.5,
                volume=1_000_000,
            ),
            PriceHistory(
                date=date.today(),
                open=62.0,
                high=63.0,
                low=61.8,
                close=62.5,
                volume=900_000,
            ),
        ],
    )

    with (
        patch.object(service, "_load_documents", return_value=({"KO": document}, {})),
        patch(
            "services.portfolio_details_service.load_portfolio_statistics_stock",
            return_value=_stats(),
        ),
        patch.object(service, "_get_price_snapshot", return_value=_empty_snapshot()),
        patch.object(service, "_get_market_extras", return_value=(None, None, None)),
    ):
        rows, _ = service.build_rows_with_cache(
            use_live_prices=False,
            preload_analysis=False,
        )

    assert rows[0].current_price == 62.5
    assert rows[0].previous_close == 61.5
    assert rows[0].current_value == 625.0


def test_build_rows_with_live_prices_falls_back_to_history_previous_close(
    portfolio_store: PortfolioStore,
) -> None:
    from datetime import date

    from data_ingestion.models import PriceHistory, StockDocument

    portfolio_store.upsert_holding(
        "KO",
        shares=10,
        avg_cost_per_share=50.0,
        company_name="Coca-Cola Co",
    )
    service = PortfolioDetailsService(store=portfolio_store)
    document = StockDocument(
        symbol="KO",
        name="Coca-Cola Co",
        current_price=62.5,
        price_history=[
            PriceHistory(
                date=date(2026, 5, 18),
                open=61.0,
                high=62.0,
                low=60.5,
                close=61.5,
                volume=1_000_000,
            ),
            PriceHistory(
                date=date.today(),
                open=62.0,
                high=63.0,
                low=61.8,
                close=62.5,
                volume=900_000,
            ),
        ],
    )

    with (
        patch.object(service, "_load_documents", return_value=({"KO": document}, {})),
        patch(
            "services.portfolio_details_service.load_portfolio_statistics_stock",
            return_value=_stats(),
        ),
        patch(
            "services.portfolio_details_service.fetch_latest_market_price",
            return_value=650.0,
        ),
        patch(
            "services.portfolio_details_service.fetch_previous_close",
            return_value=None,
        ),
        patch.object(service, "_get_price_snapshot", return_value=_empty_snapshot()),
        patch.object(service, "_get_market_extras", return_value=(None, None, None)),
    ):
        rows, _ = service.build_rows_with_cache(
            use_live_prices=True,
            preload_analysis=False,
        )

    assert rows[0].current_price == 650.0
    assert rows[0].previous_close == 61.5


def test_build_rows_with_live_prices_sets_previous_close(portfolio_store: PortfolioStore) -> None:
    portfolio_store.upsert_holding(
        "KO",
        shares=10,
        avg_cost_per_share=50.0,
        company_name="Coca-Cola Co",
    )
    service = PortfolioDetailsService(store=portfolio_store)

    with (
        patch.object(service, "_load_documents", return_value=({}, {})),
        patch(
            "services.portfolio_details_service.load_portfolio_statistics_stock",
            return_value=_stats(),
        ),
        patch(
            "services.portfolio_details_service.fetch_latest_market_price",
            return_value=650.0,
        ),
        patch(
            "services.portfolio_details_service.fetch_previous_close",
            return_value=645.0,
        ),
        patch.object(service, "_get_price_snapshot", return_value=_empty_snapshot()),
        patch.object(service, "_get_market_extras", return_value=(None, None, None)),
    ):
        rows, _ = service.build_rows_with_cache(
            use_live_prices=True,
            preload_analysis=False,
        )

    assert rows[0].current_price == 650.0
    assert rows[0].previous_close == 645.0
    assert rows[0].current_value == 6500.0


def test_build_rows_preloads_analysis_when_enabled(portfolio_store: PortfolioStore) -> None:
    portfolio_store.upsert_holding("KO", shares=10, avg_cost_per_share=50.0)
    service = PortfolioDetailsService(store=portfolio_store)
    preload = PortfolioAnalysisPreload(stock_data={}, yield_channels={}, vector_docs={})

    with (
        patch.object(service, "_load_documents", return_value=({}, {})),
        patch(
            "services.portfolio_details_service.load_portfolio_statistics_stock",
            return_value=_stats(),
        ),
        patch.object(service, "_get_price_snapshot", return_value=_empty_snapshot()),
        patch.object(service, "_get_market_extras", return_value=(None, None, None)),
        patch(
            "services.portfolio_details_service.preload_portfolio_analysis",
            return_value=preload,
        ) as mock_preload,
    ):
        _, result = service.build_rows_with_cache(preload_analysis=True)

    mock_preload.assert_called_once()
    assert result.stock_data == preload.stock_data
    assert result.yield_channels == preload.yield_channels
    assert result.vector_docs == preload.vector_docs
    assert result.dividend_statuses == {}
