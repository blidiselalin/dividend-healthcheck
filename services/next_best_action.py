"""
Resolve a single next-best action for the portfolio dashboard.

Pure logic (no Streamlit) so priority rules stay unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReconciliationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NextBestActionContext:
    has_portfolio: bool
    has_successful_import: bool
    latest_import_failed: bool
    import_warning_count: int
    has_blocking_import_errors: bool
    reconciliation_status: str
    has_dividend_transactions: bool
    has_viewed_dividend_dashboard: bool
    has_upcoming_dividends: bool
    preferences_configured: bool


@dataclass(frozen=True)
class NextBestAction:
    id: str
    title: str
    description: str
    primary_action_label: str
    primary_action_route: str
    secondary_action_label: str | None
    secondary_action_route: str | None
    severity: str  # info | warning | error


def resolve_next_best_action(context: NextBestActionContext) -> NextBestAction:
    """Return exactly one primary action using the product priority order."""
    if not context.has_portfolio:
        return NextBestAction(
            id="add_portfolio",
            title="Add your first portfolio",
            description=(
                "Import an Interactive Brokers Activity Statement CSV, or add a ticker "
                "manually, so we can track holdings and dividend income."
            ),
            primary_action_label="Import from IBKR",
            primary_action_route="manage:import",
            secondary_action_label="Add ticker manually",
            secondary_action_route="manage",
            severity="info",
        )

    if not context.has_successful_import:
        return NextBestAction(
            id="import_broker_data",
            title="Import broker data",
            description=(
                "Upload an Interactive Brokers activity statement to load trades, "
                "dividends, and deposits."
            ),
            primary_action_label="Import broker data",
            primary_action_route="manage:import",
            secondary_action_label="What we can import",
            secondary_action_route="help:importing",
            severity="info",
        )

    if context.latest_import_failed or context.has_blocking_import_errors:
        return NextBestAction(
            id="retry_import",
            title="Retry your broker import",
            description=(
                "The latest import did not finish cleanly. Fix the file or validation "
                "issues, then import again."
            ),
            primary_action_label="Retry import",
            primary_action_route="manage:import",
            secondary_action_label="How importing works",
            secondary_action_route="help:importing",
            severity="error",
        )

    if context.import_warning_count > 0:
        return NextBestAction(
            id="review_import_issues",
            title="Review import issues",
            description=(
                "Your import was saved, but some transactions need attention before "
                "totals look complete."
            ),
            primary_action_label="Review issues",
            primary_action_route="manage:import_issues",
            secondary_action_label="How reconciliation works",
            secondary_action_route="help:reconciliation",
            severity="warning",
        )

    if context.reconciliation_status not in (
        ReconciliationStatus.SUCCESS,
        ReconciliationStatus.UNKNOWN,
    ):
        return NextBestAction(
            id="review_reconciliation",
            title="Verify your imported portfolio",
            description=(
                "We found differences between imported transactions and current holdings."
            ),
            primary_action_label="Review issues",
            primary_action_route="manage:import_issues",
            secondary_action_label="How reconciliation works",
            secondary_action_route="help:reconciliation",
            severity="warning",
        )

    if not context.has_dividend_transactions:
        return NextBestAction(
            id="check_dividend_data",
            title="Check imported dividend data",
            description=(
                "Dividend history comes from broker cash transactions, not from " "holdings alone."
            ),
            primary_action_label="Import dividend transactions",
            primary_action_route="manage:import",
            secondary_action_label="How dividends are calculated",
            secondary_action_route="help:dividends",
            severity="info",
        )

    if not context.has_viewed_dividend_dashboard:
        return NextBestAction(
            id="review_dividend_income",
            title="Review dividend income",
            description=(
                "Open the dividend dashboard to separate received, accrued, and " "estimated cash."
            ),
            primary_action_label="Review dividend income",
            primary_action_route="dividends",
            secondary_action_label="Received vs estimated",
            secondary_action_route="help:received_vs_estimated",
            severity="info",
        )

    if context.has_upcoming_dividends:
        return NextBestAction(
            id="view_upcoming_dividends",
            title="View upcoming dividends",
            description=("Ex-dates and payment dates are available for your current holdings."),
            primary_action_label="View upcoming dividends",
            primary_action_route="dashboard",
            secondary_action_label="Dividend terms",
            secondary_action_route="help:dividends",
            severity="info",
        )

    return NextBestAction(
        id="review_month_income",
        title="Review this month's income",
        description=(
            "Your portfolio is set up. Check estimated and received dividends for "
            "the current month."
        ),
        primary_action_label="Review this month's income",
        primary_action_route="dividends",
        secondary_action_label="Open help",
        secondary_action_route="help:getting_started",
        severity="info",
    )


def build_next_best_action_context(
    *,
    has_portfolio: bool,
    has_successful_import: bool,
    latest_import_failed: bool = False,
    import_warning_count: int = 0,
    has_blocking_import_errors: bool = False,
    reconciliation_status: str = ReconciliationStatus.UNKNOWN,
    has_dividend_transactions: bool = False,
    has_viewed_dividend_dashboard: bool = False,
    has_upcoming_dividends: bool = False,
    preferences_configured: bool = False,
) -> NextBestActionContext:
    return NextBestActionContext(
        has_portfolio=has_portfolio,
        has_successful_import=has_successful_import,
        latest_import_failed=latest_import_failed,
        import_warning_count=max(0, int(import_warning_count)),
        has_blocking_import_errors=has_blocking_import_errors,
        reconciliation_status=str(reconciliation_status or ReconciliationStatus.UNKNOWN),
        has_dividend_transactions=has_dividend_transactions,
        has_viewed_dividend_dashboard=has_viewed_dividend_dashboard,
        has_upcoming_dividends=has_upcoming_dividends,
        preferences_configured=preferences_configured,
    )
