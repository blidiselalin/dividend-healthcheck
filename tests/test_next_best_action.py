"""Unit tests for next-best-action priority resolution."""

from __future__ import annotations

from services.next_best_action import (
    ReconciliationStatus,
    build_next_best_action_context,
    resolve_next_best_action,
)


def test_no_portfolio_adds_portfolio() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=False,
            has_successful_import=False,
        )
    )
    assert action.id == "add_portfolio"
    assert action.primary_action_route == "manage:import"


def test_portfolio_without_data_imports() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=False,
        )
    )
    assert action.id == "import_broker_data"


def test_failed_import_retries() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=True,
            latest_import_failed=True,
        )
    )
    assert action.id == "retry_import"


def test_import_warnings_review_issues() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=True,
            import_warning_count=2,
        )
    )
    assert action.id == "review_import_issues"
    assert action.primary_action_label == "Review issues"


def test_reconciliation_failure_review() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=True,
            reconciliation_status=ReconciliationStatus.FAILED,
        )
    )
    assert action.id == "review_reconciliation"


def test_no_dividend_transactions() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=True,
            has_dividend_transactions=False,
        )
    )
    assert action.id == "check_dividend_data"


def test_dividends_exist_but_dashboard_not_viewed() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=True,
            has_dividend_transactions=True,
            has_viewed_dividend_dashboard=False,
        )
    )
    assert action.id == "review_dividend_income"
    assert action.primary_action_route == "dividends"


def test_upcoming_dividends_available() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=True,
            has_dividend_transactions=True,
            has_viewed_dividend_dashboard=True,
            has_upcoming_dividends=True,
        )
    )
    assert action.id == "view_upcoming_dividends"


def test_fully_configured_reviews_month_income() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=True,
            has_dividend_transactions=True,
            has_viewed_dividend_dashboard=True,
            has_upcoming_dividends=False,
            preferences_configured=True,
        )
    )
    assert action.id == "review_month_income"


def test_import_warnings_override_educational_actions() -> None:
    action = resolve_next_best_action(
        build_next_best_action_context(
            has_portfolio=True,
            has_successful_import=True,
            import_warning_count=1,
            has_dividend_transactions=True,
            has_viewed_dividend_dashboard=False,
            has_upcoming_dividends=True,
        )
    )
    assert action.id == "review_import_issues"
