"""Tests for new-user onboarding step progress."""

from __future__ import annotations

from services.portfolio_onboarding import (
    ONBOARDING_DISMISSED_KEY,
    ONBOARDING_LIVE_RELOAD_KEY,
    REAL_USER_ONBOARDING_STEPS,
    completed_step_count,
    current_sidebar_hint,
    is_step_complete,
    onboarding_complete,
    should_show_onboarding,
)


def test_real_user_steps_cover_architecture_flow() -> None:
    ids = [step.id for step in REAL_USER_ONBOARDING_STEPS]
    assert ids == ["add_holding", "background_load", "live_reload", "explore"]


def test_step_progress_empty_session() -> None:
    session: dict = {}
    done, total = completed_step_count(has_holdings=False, session=session, is_demo=False)
    assert done == 0
    assert total == len(REAL_USER_ONBOARDING_STEPS)
    assert should_show_onboarding(has_holdings=False, session=session, is_demo=False)


def test_background_load_complete_when_rows_in_session() -> None:
    session = {"portfolio_details_rows": [{"ticker": "KO"}]}
    assert is_step_complete("add_holding", has_holdings=True, session=session)
    assert is_step_complete("background_load", has_holdings=True, session=session)
    assert not is_step_complete("live_reload", has_holdings=True, session=session)


def test_live_reload_complete_when_analysis_ready() -> None:
    session = {
        "portfolio_details_rows": [{"ticker": "KO"}],
        "portfolio_analysis_ready": True,
    }
    assert is_step_complete("live_reload", has_holdings=True, session=session)
    assert onboarding_complete(has_holdings=True, session=session, is_demo=False)


def test_live_reload_complete_when_user_clicked_reload() -> None:
    session = {
        "portfolio_details_rows": [{"ticker": "KO"}],
        ONBOARDING_LIVE_RELOAD_KEY: True,
    }
    assert is_step_complete("live_reload", has_holdings=True, session=session)


def test_onboarding_hidden_when_dismissed() -> None:
    session = {ONBOARDING_DISMISSED_KEY: True}
    assert not should_show_onboarding(has_holdings=False, session=session, is_demo=False)
    assert current_sidebar_hint(has_holdings=False, session=session, is_demo=False) is None


def test_sidebar_hint_points_to_first_incomplete_step() -> None:
    session: dict = {}
    hint = current_sidebar_hint(has_holdings=False, session=session, is_demo=False)
    assert hint == REAL_USER_ONBOARDING_STEPS[0].sidebar_hint

    session = {"portfolio_details_rows": [{"ticker": "KO"}]}
    hint = current_sidebar_hint(has_holdings=True, session=session, is_demo=False)
    assert "Reload live data" in (hint or "")
