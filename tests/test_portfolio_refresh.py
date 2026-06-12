"""Tests for portfolio cache invalidation helpers."""
# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.portfolio_refresh import invalidate_section_caches, make_section_refresher


def test_invalidate_dividend_growth_cache() -> None:
    mock_growth = MagicMock()
    mock_benchmark = MagicMock()

    with (
        patch(
            "ui.portfolio_details_view._load_dividend_growth",
            mock_growth,
        ),
        patch(
            "ui.portfolio_details_view._load_benchmark_comparison",
            mock_benchmark,
        ),
    ):
        invalidate_section_caches(["journal"])
        mock_growth.clear.assert_not_called()
        mock_benchmark.clear.assert_not_called()

        invalidate_section_caches(["dividend_growth"])
        mock_growth.clear.assert_called_once()
        mock_benchmark.clear.assert_not_called()

        invalidate_section_caches(["deposits"])
        mock_benchmark.clear.assert_called_once()


def test_invalidate_all_clears_both_caches() -> None:
    mock_growth = MagicMock()
    mock_benchmark = MagicMock()
    with (
        patch("ui.portfolio_details_view._load_dividend_growth", mock_growth),
        patch(
            "ui.portfolio_details_view._load_benchmark_comparison",
            mock_benchmark,
        ),
    ):
        invalidate_section_caches(["all"])
        mock_growth.clear.assert_called_once()
        mock_benchmark.clear.assert_called_once()


def test_section_refresher_full_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_reload = MagicMock()
    mock_rerun = MagicMock()
    mock_spinner = MagicMock()
    mock_spinner.__enter__ = MagicMock(return_value=None)
    mock_spinner.__exit__ = MagicMock(return_value=None)

    import streamlit as st

    monkeypatch.setattr(st, "spinner", lambda *a, **k: mock_spinner)
    monkeypatch.setattr(st, "rerun", mock_rerun)
    with patch("services.portfolio_refresh.reload_portfolio_session", mock_reload):
        make_section_refresher("holdings")()
    mock_reload.assert_called_once()
    mock_rerun.assert_called_once()
