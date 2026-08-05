"""
New-user onboarding progress — checklist + context for next-best actions.

Logic only (no Streamlit imports) so step completion is unit-testable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from services.next_best_action import (
    NextBestActionContext,
    ReconciliationStatus,
    build_next_best_action_context,
)

ONBOARDING_DISMISSED_KEY = "portfolio_onboarding_dismissed"
ONBOARDING_LIVE_RELOAD_KEY = "portfolio_onboarding_live_reload"
VIEWED_DIVIDEND_DASHBOARD_KEY = "guidance_viewed_dividend_dashboard"
VIEWED_UPCOMING_DIVIDENDS_KEY = "guidance_viewed_upcoming_dividends"
PREFERENCES_CONFIGURED_KEY = "guidance_preferences_configured"
LAST_IMPORT_SUMMARY_KEY = "guidance_last_import_summary"
ONBOARDING_STEP_EVENTS_KEY = "portfolio_onboarding_step_events"


class StepStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"


class ChecklistStepId(StrEnum):
    ADD_PORTFOLIO = "ADD_PORTFOLIO"
    IMPORT_DATA = "IMPORT_DATA"
    VERIFY_DATA = "VERIFY_DATA"
    REVIEW_DIVIDENDS = "REVIEW_DIVIDENDS"
    VIEW_UPCOMING_DIVIDENDS = "VIEW_UPCOMING_DIVIDENDS"
    CONFIGURE_PREFERENCES = "CONFIGURE_PREFERENCES"


@dataclass(frozen=True)
class OnboardingStep:
    id: str
    title: str
    detail: str
    sidebar_hint: str
    description: str = ""
    action_label: str = ""
    action_route: str = ""
    is_required: bool = True

    def __post_init__(self) -> None:
        if not self.description:
            object.__setattr__(self, "description", self.detail)


@dataclass(frozen=True)
class ChecklistStepState:
    id: str
    title: str
    description: str
    status: StepStatus
    action_label: str
    action_route: str
    is_required: bool


REAL_USER_ONBOARDING_STEPS: tuple[OnboardingStep, ...] = (
    OnboardingStep(
        id=ChecklistStepId.ADD_PORTFOLIO,
        title="Add your portfolio",
        detail=(
            "Preferred: **Manage portfolio** → **Import IBKR** with an Activity Statement CSV. "
            "Or add a single ticker under **Add ticker** if you only need a quick start."
        ),
        sidebar_hint="Open **Manage portfolio** → **Import IBKR** (or Add ticker).",
        action_label="Import from IBKR",
        action_route="manage:import",
    ),
    OnboardingStep(
        id=ChecklistStepId.IMPORT_DATA,
        title="Import from IBKR",
        detail=(
            "Download an **Activity Statement** CSV (AS_Fv2) from IBKR, then use "
            "**Manage portfolio** → **Import IBKR**: upload → choose Merge or Full replace → "
            "review preview → **Apply import**. Loads trades, dividends, withholding, "
            "deposits, fees, and positions when available."
        ),
        sidebar_hint="Sidebar → **Manage portfolio** → **Import IBKR** → upload AS_Fv2 CSV.",
        action_label="Open Import IBKR",
        action_route="manage:import",
    ),
    OnboardingStep(
        id=ChecklistStepId.VERIFY_DATA,
        title="Verify imported data",
        detail=(
            "After Apply import, check warnings on the **Import IBKR** tab. "
            "Fix the source file or re-import if validation or reconciliation issues remain."
        ),
        sidebar_hint="Review import warnings under **Manage portfolio** → **Import IBKR**.",
        action_label="Review import issues",
        action_route="manage:import_issues",
    ),
    OnboardingStep(
        id=ChecklistStepId.REVIEW_DIVIDENDS,
        title="Review dividend income",
        detail=(
            "Open **Dividend income** once broker dividend receipts exist. "
            "Received, accrued, and estimated cash stay separate."
        ),
        sidebar_hint="Open **Dividend income** to review received vs estimated cash.",
        action_label="Review dividends",
        action_route="dividends",
    ),
    OnboardingStep(
        id=ChecklistStepId.VIEW_UPCOMING_DIVIDENDS,
        title="View upcoming dividends",
        detail="Open Home watchlists to see upcoming ex-dates and payment dates.",
        sidebar_hint="Check upcoming ex-dates on **Home**.",
        action_label="View upcoming",
        action_route="dashboard",
    ),
    OnboardingStep(
        id=ChecklistStepId.CONFIGURE_PREFERENCES,
        title="Configure preferences",
        detail=(
            "Open **Background tasks** and choose whether automatic refresh runs on load. "
            "You can keep the default (off) and mark this step done."
        ),
        sidebar_hint="Set background-task preferences in the sidebar.",
        action_label="Open preferences",
        action_route="preferences",
        is_required=False,
    ),
)

DEMO_ONBOARDING_STEPS: tuple[OnboardingStep, ...] = (
    OnboardingStep(
        id="load_demo",
        title="Load the demo portfolio",
        detail="Click **Load demo portfolio** — sample holdings KO, JNJ, and O load instantly.",
        sidebar_hint="Load the demo portfolio from Home.",
        action_label="Load demo",
        action_route="dashboard",
    ),
    OnboardingStep(
        id="try_examples",
        title="Try the guided examples",
        detail="Open **Try it — 3 quick examples** on Home to jump to analysis and income views.",
        sidebar_hint="Expand **Try it — 3 quick examples** on Home.",
        action_label="Show examples",
        action_route="dashboard",
    ),
    OnboardingStep(
        id="live_reload",
        title="Reload live data",
        detail=(
            "Use **Reload live data** in the sidebar to refresh prices and charts "
            "in the background."
        ),
        sidebar_hint="Click **Reload live data** in the sidebar.",
        action_label="Reload live data",
        action_route="preferences",
    ),
)


def _session_get(session: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return session.get(key, default)
    except AttributeError:
        return default


def _last_import_summary(session: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = _session_get(session, LAST_IMPORT_SUMMARY_KEY) or {}
    return raw if isinstance(raw, Mapping) else {}


def guidance_flags_from_session(session: Mapping[str, Any]) -> dict[str, Any]:
    """Derive import / view flags from session-cached guidance state."""
    summary = _last_import_summary(session)
    warning_count = int(summary.get("warning_count") or 0)
    blocking = bool(summary.get("blocking_error_count") or 0)
    failed = bool(summary.get("failed"))
    reconciliation = str(summary.get("reconciliation_status") or ReconciliationStatus.UNKNOWN)
    successful = bool(summary.get("successful")) or bool(summary.get("imported_records"))
    return {
        "has_successful_import": successful,
        "latest_import_failed": failed,
        "import_warning_count": warning_count,
        "has_blocking_import_errors": blocking,
        "reconciliation_status": reconciliation,
        "has_viewed_dividend_dashboard": bool(_session_get(session, VIEWED_DIVIDEND_DASHBOARD_KEY)),
        "has_viewed_upcoming_dividends": bool(_session_get(session, VIEWED_UPCOMING_DIVIDENDS_KEY)),
        "preferences_configured": bool(_session_get(session, PREFERENCES_CONFIGURED_KEY))
        or ("background_tasks_auto_enabled" in session),
    }


def build_guidance_context(
    *,
    has_portfolio: bool,
    has_dividend_transactions: bool,
    has_upcoming_dividends: bool,
    session: Mapping[str, Any],
    has_successful_import: bool | None = None,
) -> NextBestActionContext:
    flags = guidance_flags_from_session(session)
    successful = (
        flags["has_successful_import"] if has_successful_import is None else has_successful_import
    )
    # Manual ticker add counts as a portfolio; import step still tracks broker data.
    if has_portfolio and has_successful_import is None and not successful:
        # Journal/receipt-derived success is passed by callers when available.
        successful = bool(flags["has_successful_import"])
    return build_next_best_action_context(
        has_portfolio=has_portfolio,
        has_successful_import=successful,
        latest_import_failed=flags["latest_import_failed"],
        import_warning_count=flags["import_warning_count"],
        has_blocking_import_errors=flags["has_blocking_import_errors"],
        reconciliation_status=flags["reconciliation_status"],
        has_dividend_transactions=has_dividend_transactions,
        has_viewed_dividend_dashboard=flags["has_viewed_dividend_dashboard"],
        has_upcoming_dividends=has_upcoming_dividends,
        preferences_configured=flags["preferences_configured"],
    )


def _verify_status(context: NextBestActionContext) -> StepStatus:
    if not context.has_successful_import and not context.latest_import_failed:
        return StepStatus.NOT_STARTED
    needs_attention = (
        context.latest_import_failed
        or context.has_blocking_import_errors
        or context.import_warning_count > 0
        or context.reconciliation_status
        not in (ReconciliationStatus.SUCCESS, ReconciliationStatus.UNKNOWN)
    )
    if needs_attention:
        return StepStatus.NEEDS_ATTENTION
    if context.has_successful_import:
        return StepStatus.COMPLETED
    return StepStatus.IN_PROGRESS


def _review_dividends_status(context: NextBestActionContext) -> StepStatus:
    if not context.has_dividend_transactions:
        return StepStatus.IN_PROGRESS if context.has_successful_import else StepStatus.NOT_STARTED
    if context.has_viewed_dividend_dashboard:
        return StepStatus.COMPLETED
    return StepStatus.IN_PROGRESS


def _demo_step_status(step_id: str, session: Mapping[str, Any]) -> StepStatus | None:
    if step_id == "load_demo":
        return (
            StepStatus.COMPLETED
            if bool(_session_get(session, "portfolio_details_rows"))
            else StepStatus.NOT_STARTED
        )
    if step_id == "try_examples":
        return (
            StepStatus.COMPLETED
            if bool(_session_get(session, "portfolio_show_examples"))
            else StepStatus.NOT_STARTED
        )
    if step_id == "live_reload":
        ready = bool(_session_get(session, "portfolio_analysis_ready")) or bool(
            _session_get(session, ONBOARDING_LIVE_RELOAD_KEY)
        )
        return StepStatus.COMPLETED if ready else StepStatus.NOT_STARTED
    return None


def step_status_for(
    step_id: str,
    *,
    context: NextBestActionContext,
    session: Mapping[str, Any],
) -> StepStatus:
    flags = guidance_flags_from_session(session)
    if step_id == ChecklistStepId.ADD_PORTFOLIO:
        return StepStatus.COMPLETED if context.has_portfolio else StepStatus.NOT_STARTED
    if step_id == ChecklistStepId.IMPORT_DATA:
        if context.has_successful_import:
            return StepStatus.COMPLETED
        return StepStatus.IN_PROGRESS if context.has_portfolio else StepStatus.NOT_STARTED
    if step_id == ChecklistStepId.VERIFY_DATA:
        return _verify_status(context)
    if step_id == ChecklistStepId.REVIEW_DIVIDENDS:
        return _review_dividends_status(context)
    if step_id == ChecklistStepId.VIEW_UPCOMING_DIVIDENDS:
        if flags["has_viewed_upcoming_dividends"]:
            return StepStatus.COMPLETED
        return StepStatus.IN_PROGRESS if context.has_portfolio else StepStatus.NOT_STARTED
    if step_id == ChecklistStepId.CONFIGURE_PREFERENCES:
        return StepStatus.COMPLETED if context.preferences_configured else StepStatus.NOT_STARTED
    demo_status = _demo_step_status(step_id, session)
    return demo_status if demo_status is not None else StepStatus.NOT_STARTED


def is_step_complete(
    step_id: str,
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
    has_dividend_transactions: bool = False,
    has_upcoming_dividends: bool = False,
    has_successful_import: bool | None = None,
) -> bool:
    """Return True when an onboarding step is satisfied."""
    if is_demo:
        status = step_status_for(
            step_id,
            context=build_guidance_context(
                has_portfolio=has_holdings,
                has_dividend_transactions=has_dividend_transactions,
                has_upcoming_dividends=has_upcoming_dividends,
                session=session,
                has_successful_import=has_successful_import,
            ),
            session=session,
        )
        return status == StepStatus.COMPLETED

    context = build_guidance_context(
        has_portfolio=has_holdings,
        has_dividend_transactions=has_dividend_transactions,
        has_upcoming_dividends=has_upcoming_dividends,
        session=session,
        has_successful_import=has_successful_import,
    )
    return step_status_for(step_id, context=context, session=session) == StepStatus.COMPLETED


def checklist_states(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
    has_dividend_transactions: bool = False,
    has_upcoming_dividends: bool = False,
    has_successful_import: bool | None = None,
) -> list[ChecklistStepState]:
    context = build_guidance_context(
        has_portfolio=has_holdings,
        has_dividend_transactions=has_dividend_transactions,
        has_upcoming_dividends=has_upcoming_dividends,
        session=session,
        has_successful_import=has_successful_import,
    )
    steps = onboarding_steps(is_demo=is_demo)
    return [
        ChecklistStepState(
            id=step.id,
            title=step.title,
            description=step.description or step.detail,
            status=step_status_for(step.id, context=context, session=session),
            action_label=step.action_label,
            action_route=step.action_route,
            is_required=step.is_required,
        )
        for step in steps
    ]


def onboarding_steps(*, is_demo: bool) -> Sequence[OnboardingStep]:
    return DEMO_ONBOARDING_STEPS if is_demo else REAL_USER_ONBOARDING_STEPS


def step_progress(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
    has_dividend_transactions: bool = False,
    has_upcoming_dividends: bool = False,
    has_successful_import: bool | None = None,
) -> list[tuple[OnboardingStep, bool]]:
    steps = onboarding_steps(is_demo=is_demo)
    return [
        (
            step,
            is_step_complete(
                step.id,
                has_holdings=has_holdings,
                session=session,
                is_demo=is_demo,
                has_dividend_transactions=has_dividend_transactions,
                has_upcoming_dividends=has_upcoming_dividends,
                has_successful_import=has_successful_import,
            ),
        )
        for step in steps
    ]


def onboarding_complete(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
    has_dividend_transactions: bool = False,
    has_upcoming_dividends: bool = False,
    has_successful_import: bool | None = None,
) -> bool:
    states = checklist_states(
        has_holdings=has_holdings,
        session=session,
        is_demo=is_demo,
        has_dividend_transactions=has_dividend_transactions,
        has_upcoming_dividends=has_upcoming_dividends,
        has_successful_import=has_successful_import,
    )
    required = [state for state in states if state.is_required]
    target = required or states
    return bool(target) and all(state.status == StepStatus.COMPLETED for state in target)


def should_show_onboarding(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
    has_dividend_transactions: bool = False,
    has_upcoming_dividends: bool = False,
    has_successful_import: bool | None = None,
) -> bool:
    if _session_get(session, ONBOARDING_DISMISSED_KEY):
        return False
    return not onboarding_complete(
        has_holdings=has_holdings,
        session=session,
        is_demo=is_demo,
        has_dividend_transactions=has_dividend_transactions,
        has_upcoming_dividends=has_upcoming_dividends,
        has_successful_import=has_successful_import,
    )


def current_sidebar_hint(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
    has_dividend_transactions: bool = False,
    has_upcoming_dividends: bool = False,
    has_successful_import: bool | None = None,
) -> str | None:
    if not should_show_onboarding(
        has_holdings=has_holdings,
        session=session,
        is_demo=is_demo,
        has_dividend_transactions=has_dividend_transactions,
        has_upcoming_dividends=has_upcoming_dividends,
        has_successful_import=has_successful_import,
    ):
        return None
    for step, done in step_progress(
        has_holdings=has_holdings,
        session=session,
        is_demo=is_demo,
        has_dividend_transactions=has_dividend_transactions,
        has_upcoming_dividends=has_upcoming_dividends,
        has_successful_import=has_successful_import,
    ):
        if not done:
            return step.sidebar_hint
    return None


def completed_step_count(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
    has_dividend_transactions: bool = False,
    has_upcoming_dividends: bool = False,
    has_successful_import: bool | None = None,
) -> tuple[int, int]:
    progress = step_progress(
        has_holdings=has_holdings,
        session=session,
        is_demo=is_demo,
        has_dividend_transactions=has_dividend_transactions,
        has_upcoming_dividends=has_upcoming_dividends,
        has_successful_import=has_successful_import,
    )
    done = sum(1 for _, complete in progress if complete)
    return done, len(progress)


def record_import_guidance_summary(
    session: dict[str, Any],
    *,
    successful: bool,
    failed: bool,
    imported_records: int,
    skipped_duplicates: int,
    updated_records: int,
    warning_count: int,
    blocking_error_count: int,
    reconciliation_status: str,
    date_range: str | None = None,
    currencies: list[str] | None = None,
    broker_account_masked: str | None = None,
) -> None:
    """Persist a non-sensitive import summary for checklist / NBA derivation."""
    session[LAST_IMPORT_SUMMARY_KEY] = {
        "successful": successful,
        "failed": failed,
        "imported_records": imported_records,
        "skipped_duplicates": skipped_duplicates,
        "updated_records": updated_records,
        "warning_count": warning_count,
        "blocking_error_count": blocking_error_count,
        "reconciliation_status": reconciliation_status,
        "date_range": date_range or "",
        "currencies": list(currencies or []),
        "broker_account_masked": broker_account_masked or "",
    }
