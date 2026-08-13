"""Home / guidance interaction helpers — selection clear, import focus, routes."""
# ruff: noqa: S101

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_clear_home_table_selections_removes_widget_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "home_positions_table": {"selection": {"rows": [0]}},
        "home_clear_dividend_risk": {"selection": {"rows": [1]}},
        "keep_me": True,
    }
    mock_st = MagicMock()
    mock_st.session_state = state
    monkeypatch.setattr("ui.portfolio_home.st", mock_st)

    from ui.portfolio_home import clear_home_table_selections
    from ui.session_keys import HOME_TABLE_SELECTION_KEYS

    clear_home_table_selections()
    for key in HOME_TABLE_SELECTION_KEYS:
        assert key not in state
    assert state["keep_me"] is True


def test_set_holding_selection_rejects_blank_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict = {}
    mock_st = MagicMock()
    mock_st.session_state = state
    monkeypatch.setattr("ui.portfolio_home.st", mock_st)

    from ui.portfolio_home import PORTFOLIO_VIEW_HOLDING, set_holding_selection

    set_holding_selection("  ")
    assert "portfolio_selected_symbol" not in state
    mock_st.rerun.assert_not_called()

    set_holding_selection("ko", nav_tickers=["ko", "jnj"])
    assert state["portfolio_selected_symbol"] == "KO"
    assert state["portfolio_view_mode"] == PORTFOLIO_VIEW_HOLDING
    assert state["portfolio_nav_tickers"] == ["KO", "JNJ"]
    mock_st.rerun.assert_called_once()


def test_navigate_guidance_import_sets_focus_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict = {}
    mock_st = MagicMock()
    mock_st.session_state = state
    monkeypatch.setattr("ui.user_guidance.st", mock_st)

    home_calls: list[str] = []

    def _fake_home() -> None:
        home_calls.append("home")

    monkeypatch.setattr("ui.portfolio_home.navigate_to_portfolio_home", _fake_home)

    from ui.user_guidance import navigate_guidance_route

    navigate_guidance_route("manage:import")
    assert state["portfolio_manage_expand"] is True
    assert state["portfolio_manage_focus_import"] is True
    assert state["portfolio_onboarding_show_manage_tip"] is True
    assert home_calls == ["home"]


def test_navigate_guidance_dividend_growth_route(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_st = MagicMock()
    mock_st.session_state = {}
    monkeypatch.setattr("ui.user_guidance.st", mock_st)

    sections: list[str] = []

    def _fake_section(key: str) -> None:
        sections.append(key)

    monkeypatch.setattr("ui.portfolio_home.navigate_to_portfolio_section", _fake_section)

    from ui.user_guidance import navigate_guidance_route

    navigate_guidance_route("dividend_growth")
    assert sections == ["dividend_growth"]


def test_open_help_drawer_syncs_topic_widget(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict = {}
    mock_st = MagicMock()
    mock_st.session_state = state
    monkeypatch.setattr("ui.user_guidance.st", mock_st)

    from ui.session_keys import (
        HELP_DRAWER_OPEN_KEY,
        HELP_DRAWER_SECTION_KEY,
        HELP_DRAWER_TOPIC_WIDGET_KEY,
    )
    from ui.user_guidance import open_help_drawer

    open_help_drawer("reconciliation")
    assert state[HELP_DRAWER_OPEN_KEY] is True
    assert state[HELP_DRAWER_SECTION_KEY] == "reconciliation"
    assert state[HELP_DRAWER_TOPIC_WIDGET_KEY] == "Data reconciliation"


def test_view_upcoming_onboarding_route() -> None:
    from services.portfolio_onboarding import (
        REAL_USER_ONBOARDING_STEPS,
        ChecklistStepId,
    )

    step = next(
        s for s in REAL_USER_ONBOARDING_STEPS if s.id == ChecklistStepId.VIEW_UPCOMING_DIVIDENDS
    )
    assert step.action_route == "dividend_growth"


def test_watch_chip_items_shape() -> None:
    from services.clear_dividend_risk import RiskLevel
    from ui.clear_dividend_risk_panel import _watch_chip_items

    row = SimpleNamespace(
        symbol="HI",
        sustainability_status="High observed risk",
        estimated_annual_income=600.0,
        main_signal="FCF payout is elevated.",
        assessment=SimpleNamespace(risk_level=RiskLevel.HIGH_OBSERVED_RISK),
    )
    items = _watch_chip_items([row])  # type: ignore[arg-type]
    assert items
    assert items[0][0] == "HI"
    assert items[0][2] == "risky"
