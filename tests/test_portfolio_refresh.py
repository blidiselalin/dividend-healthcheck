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
    mock_payload = {
        "rows": [],
        "preload": mock_preload,
        "analysis_ready": False,
        "fast_loaded": True,
    }
    mock_compute = MagicMock(return_value=mock_payload)
    mock_store = MagicMock()
    mock_rebuild = MagicMock()
    mock_schedule_sync = MagicMock()
    mock_yield = MagicMock()

    monkeypatch.setattr(
        "services.portfolio_ui_cache.compute_fast_portfolio_payload",
        mock_compute,
    )
    monkeypatch.setattr("services.portfolio_refresh.store_portfolio_payload", mock_store)
    monkeypatch.setattr(
        "services.portfolio_refresh.schedule_forced_dividend_sync",
        mock_schedule_sync,
    )
    monkeypatch.setattr(
        "services.deferred_startup.trigger_yield_preload",
        mock_yield,
    )
    monkeypatch.setattr(
        "ui.portfolio_risk_panel._rebuild_attention_from_session",
        mock_rebuild,
    )
    monkeypatch.setattr(
        "services.portfolio_ui_cache.save_session_cache",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "utils.portfolio_db.compute_portfolio_db_fingerprint",
        lambda **kwargs: "fp-test",
    )

    reload_portfolio_after_data_import(section_label="Home", refresh_risks=False)

    mock_compute.assert_called_once()
    mock_store.assert_called_once_with([], mock_preload, analysis_ready=False)
    mock_schedule_sync.assert_called_once()
    assert st.session_state["portfolio_section_label"] == "Home"
    assert st.session_state["portfolio_view_mode"] == PORTFOLIO_VIEW_OVERVIEW
    assert "portfolio_research_mode" not in st.session_state
    assert "portfolio_holdings_drill_ticker" not in st.session_state
    assert st.session_state.get("portfolio_fast_loaded") is True


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
