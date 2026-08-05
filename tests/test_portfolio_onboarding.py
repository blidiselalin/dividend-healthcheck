"""Tests for new-user onboarding step progress and checklist derivation."""

from __future__ import annotations

from services.next_best_action import ReconciliationStatus
from services.portfolio_onboarding import (
    ONBOARDING_DISMISSED_KEY,
    PREFERENCES_CONFIGURED_KEY,
    REAL_USER_ONBOARDING_STEPS,
    VIEWED_DIVIDEND_DASHBOARD_KEY,
    VIEWED_UPCOMING_DIVIDENDS_KEY,
    ChecklistStepId,
    StepStatus,
    checklist_states,
    completed_step_count,
    current_sidebar_hint,
    is_step_complete,
    onboarding_complete,
    record_import_guidance_summary,
    should_show_onboarding,
)


def test_real_user_steps_match_getting_started_checklist() -> None:
    ids = [step.id for step in REAL_USER_ONBOARDING_STEPS]
    assert ids == [
        ChecklistStepId.ADD_PORTFOLIO,
        ChecklistStepId.IMPORT_DATA,
        ChecklistStepId.VERIFY_DATA,
        ChecklistStepId.REVIEW_DIVIDENDS,
        ChecklistStepId.VIEW_UPCOMING_DIVIDENDS,
        ChecklistStepId.CONFIGURE_PREFERENCES,
    ]


def test_step_progress_empty_session() -> None:
    session: dict = {}
    done, total = completed_step_count(has_holdings=False, session=session, is_demo=False)
    assert done == 0
    assert total == len(REAL_USER_ONBOARDING_STEPS)
    assert should_show_onboarding(has_holdings=False, session=session, is_demo=False)


def test_add_portfolio_complete_when_holdings_exist() -> None:
    session: dict = {}
    assert is_step_complete(ChecklistStepId.ADD_PORTFOLIO, has_holdings=True, session=session)


def test_import_and_verify_from_persisted_summary() -> None:
    session: dict = {}
    record_import_guidance_summary(
        session,
        successful=True,
        failed=False,
        imported_records=12,
        skipped_duplicates=1,
        updated_records=2,
        warning_count=0,
        blocking_error_count=0,
        reconciliation_status=ReconciliationStatus.SUCCESS,
    )
    assert is_step_complete(
        ChecklistStepId.IMPORT_DATA,
        has_holdings=True,
        session=session,
        has_successful_import=True,
    )
    assert is_step_complete(
        ChecklistStepId.VERIFY_DATA,
        has_holdings=True,
        session=session,
        has_successful_import=True,
    )


def test_verify_needs_attention_on_warnings() -> None:
    session: dict = {}
    record_import_guidance_summary(
        session,
        successful=True,
        failed=False,
        imported_records=5,
        skipped_duplicates=0,
        updated_records=0,
        warning_count=3,
        blocking_error_count=0,
        reconciliation_status=ReconciliationStatus.WARNING,
    )
    states = checklist_states(
        has_holdings=True,
        session=session,
        has_successful_import=True,
    )
    verify = next(state for state in states if state.id == ChecklistStepId.VERIFY_DATA)
    assert verify.status == StepStatus.NEEDS_ATTENTION


def test_review_dividends_requires_view_event() -> None:
    session: dict = {}
    assert not is_step_complete(
        ChecklistStepId.REVIEW_DIVIDENDS,
        has_holdings=True,
        session=session,
        has_dividend_transactions=True,
        has_successful_import=True,
    )
    session[VIEWED_DIVIDEND_DASHBOARD_KEY] = True
    assert is_step_complete(
        ChecklistStepId.REVIEW_DIVIDENDS,
        has_holdings=True,
        session=session,
        has_dividend_transactions=True,
        has_successful_import=True,
    )


def test_onboarding_complete_with_derived_and_interaction_flags() -> None:
    session = {
        VIEWED_DIVIDEND_DASHBOARD_KEY: True,
        VIEWED_UPCOMING_DIVIDENDS_KEY: True,
        PREFERENCES_CONFIGURED_KEY: True,
    }
    record_import_guidance_summary(
        session,
        successful=True,
        failed=False,
        imported_records=10,
        skipped_duplicates=0,
        updated_records=0,
        warning_count=0,
        blocking_error_count=0,
        reconciliation_status=ReconciliationStatus.SUCCESS,
    )
    assert onboarding_complete(
        has_holdings=True,
        session=session,
        is_demo=False,
        has_dividend_transactions=True,
        has_upcoming_dividends=True,
        has_successful_import=True,
    )
    assert not should_show_onboarding(
        has_holdings=True,
        session=session,
        is_demo=False,
        has_dividend_transactions=True,
        has_upcoming_dividends=True,
        has_successful_import=True,
    )


def test_onboarding_hidden_when_dismissed() -> None:
    session = {ONBOARDING_DISMISSED_KEY: True}
    assert not should_show_onboarding(has_holdings=False, session=session, is_demo=False)
    assert current_sidebar_hint(has_holdings=False, session=session, is_demo=False) is None


def test_dismissed_onboarding_can_be_reopened() -> None:
    session = {ONBOARDING_DISMISSED_KEY: True}
    assert not should_show_onboarding(has_holdings=False, session=session, is_demo=False)
    session[ONBOARDING_DISMISSED_KEY] = False
    assert should_show_onboarding(has_holdings=False, session=session, is_demo=False)


def test_completed_onboarding_remains_completed_after_refresh() -> None:
    session = {
        VIEWED_DIVIDEND_DASHBOARD_KEY: True,
        VIEWED_UPCOMING_DIVIDENDS_KEY: True,
        PREFERENCES_CONFIGURED_KEY: True,
    }
    record_import_guidance_summary(
        session,
        successful=True,
        failed=False,
        imported_records=4,
        skipped_duplicates=0,
        updated_records=0,
        warning_count=0,
        blocking_error_count=0,
        reconciliation_status=ReconciliationStatus.SUCCESS,
    )
    assert onboarding_complete(
        has_holdings=True,
        session=session,
        has_dividend_transactions=True,
        has_successful_import=True,
    )
    # Simulate refresh: same derived session payload, no extra UI state.
    refreshed = dict(session)
    assert onboarding_complete(
        has_holdings=True,
        session=refreshed,
        has_dividend_transactions=True,
        has_successful_import=True,
    )


def test_sidebar_hint_points_to_first_incomplete_step() -> None:
    session: dict = {}
    hint = current_sidebar_hint(has_holdings=False, session=session, is_demo=False)
    assert hint == REAL_USER_ONBOARDING_STEPS[0].sidebar_hint
