"""Tests for portfolio cache invalidation helpers."""
# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.portfolio_refresh import (
    invalidate_section_caches,
    make_section_refresher,
    reload_portfolio_after_data_import,
    reload_portfolio_session,
)


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
    mock_schedule = MagicMock()
    mock_rerun = MagicMock()

    import streamlit as st

    monkeypatch.setattr(st, "rerun", mock_rerun)
    with patch("services.portfolio_refresh.schedule_portfolio_reload", mock_schedule):
        make_section_refresher("holdings")()
    mock_schedule.assert_called_once_with(live_prices=True, sections=["all"])
    mock_rerun.assert_called_once()


def test_reload_portfolio_after_data_import_sets_home_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import streamlit as st

    from services.portfolio_analysis_preload import PortfolioAnalysisPreload
    from ui.portfolio_home import PORTFOLIO_VIEW_OVERVIEW

    st.session_state.clear()
    st.session_state["portfolio_research_mode"] = True
    st.session_state["portfolio_holdings_drill_ticker"] = "KO"
    mock_preload = PortfolioAnalysisPreload.from_caches()
    mock_reload = MagicMock(return_value=mock_preload)
    mock_risks = MagicMock()

    monkeypatch.setattr(
        "services.portfolio_refresh.reload_portfolio_session",
        mock_reload,
    )
    monkeypatch.setattr(
        "services.portfolio_refresh.refresh_portfolio_risks",
        mock_risks,
    )
    st.session_state["portfolio_details_rows"] = [{"ticker": "KO"}]

    reload_portfolio_after_data_import(section_label="Home", refresh_risks=True)

    mock_reload.assert_called_once_with(refresh_risks=False, sections=["all"])
    mock_risks.assert_called_once()
    assert st.session_state["portfolio_section_label"] == "Home"
    assert st.session_state["portfolio_view_mode"] == PORTFOLIO_VIEW_OVERVIEW
    assert "portfolio_research_mode" not in st.session_state
    assert "portfolio_holdings_drill_ticker" not in st.session_state


def test_reload_portfolio_session_resets_view_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import streamlit as st

    from services.portfolio_analysis_preload import PortfolioAnalysisPreload

    reset_calls: list[bool] = []
    mock_preload = PortfolioAnalysisPreload.from_caches()

    monkeypatch.setattr(
        "services.portfolio_session.reset_portfolio_view_state",
        lambda: reset_calls.append(True),
    )
    monkeypatch.setattr(
        "services.portfolio_refresh.clear_session_cache",
        lambda: None,
    )
    monkeypatch.setattr(
        "services.portfolio_refresh.schedule_forced_dividend_sync",
        lambda: None,
    )
    monkeypatch.setattr(
        "services.portfolio_refresh.refresh_portfolio_risks",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "services.portfolio_refresh.store_portfolio_payload",
        lambda rows, preload: None,
    )
    monkeypatch.setattr(
        "services.portfolio_refresh.PortfolioDetailsService",
        lambda: type(
            "Svc",
            (),
            {
                "build_rows_with_cache": lambda self, **kwargs: ([], mock_preload),
            },
        )(),
    )
    monkeypatch.setattr(
        "utils.portfolio_db.compute_portfolio_db_fingerprint",
        lambda **kwargs: "fp-test",
    )

    st.session_state.clear()
    reload_portfolio_session(refresh_risks=False)

    assert reset_calls == [True]
    assert st.session_state["_portfolio_db_fingerprint"] == "fp-test"
