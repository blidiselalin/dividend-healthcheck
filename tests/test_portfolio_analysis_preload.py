"""Tests for portfolio yield-chart preload."""
# ruff: noqa: S101

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from services.portfolio_analysis_preload import preload_portfolio_analysis


def test_preload_empty_symbols() -> None:
    result = preload_portfolio_analysis([], {}, {})
    assert result.yield_channels == {}
    assert result.stock_data == {}
    assert result.vector_docs == {}


@patch("services.stock_analysis_service.load_yield_channel_data")
def test_preload_collects_channels(mock_fetch: Any) -> None:
    channel = MagicMock()
    mock_fetch.return_value = channel
    stock = MagicMock()
    doc = MagicMock()

    result = preload_portfolio_analysis(
        ["KO", "PEP"],
        {"KO": stock, "PEP": stock},
        {"KO": doc},
    )

    assert result.yield_channels == {"KO": channel, "PEP": channel}
    assert mock_fetch.call_count == 2


@patch("services.stock_analysis_service.load_yield_channel_data")
def test_preload_skips_failed_symbols(mock_fetch: Any) -> None:
    mock_fetch.side_effect = [MagicMock(), RuntimeError("network")]
    progress = MagicMock()

    result = preload_portfolio_analysis(
        ["KO", "PEP"],
        {},
        {},
        progress_callback=progress,
    )

    assert list(result.yield_channels) == ["KO"]
    assert progress.call_count >= 2


@patch("utils.stock_document_history.history_is_thin", return_value=False)
@patch("services.stock_analysis_service.load_yield_channel_data", return_value=MagicMock())
@patch("services.portfolio_details_service.PortfolioDetailsService._load_documents")
def test_preload_loads_dividend_statuses_when_docs_cached(
    mock_load_documents: Any,
    mock_fetch: Any,
    mock_history_is_thin: Any,
) -> None:
    doc = MagicMock()
    status = MagicMock()
    mock_load_documents.return_value = ({"KO": doc}, {"KO": status})

    result = preload_portfolio_analysis(
        ["KO"],
        {},
        {"KO": doc},
        dividend_statuses={},
    )

    mock_load_documents.assert_called_once_with(["KO"])
    assert result.dividend_statuses == {"KO": status}
    assert result.vector_docs == {"KO": doc}


@patch("services.stock_analysis_service.load_yield_channel_data", return_value=MagicMock())
def test_preload_reports_progress(mock_fetch: Any) -> None:
    progress = MagicMock()
    preload_portfolio_analysis(["KO"], {}, {}, progress_callback=progress)
    assert progress.call_args_list[0][0][0] == 0.0
    assert progress.call_args_list[-1][0][0] == 1.0
