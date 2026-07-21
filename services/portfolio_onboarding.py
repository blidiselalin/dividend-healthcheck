"""
New-user onboarding progress — aligned with background portfolio load architecture.

Logic only (no Streamlit imports) so step completion is unit-testable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

ONBOARDING_DISMISSED_KEY = "portfolio_onboarding_dismissed"
ONBOARDING_LIVE_RELOAD_KEY = "portfolio_onboarding_live_reload"


@dataclass(frozen=True)
class OnboardingStep:
    id: str
    title: str
    detail: str
    sidebar_hint: str


REAL_USER_ONBOARDING_STEPS: tuple[OnboardingStep, ...] = (
    OnboardingStep(
        id="add_holding",
        title="Add your first ticker",
        detail=(
            "In the sidebar, open **Manage portfolio** → **Add ticker**. "
            "Enter a symbol (e.g. `VZ`, `KO`), share count, and average cost per share, "
            "then click **Add to portfolio**."
        ),
        sidebar_hint="Open **Manage portfolio** in the sidebar and add your first ticker.",
    ),
    OnboardingStep(
        id="background_load",
        title="Let the background load finish",
        detail=(
            "After you save, holdings refresh **automatically in the background** — "
            "watch **Background tasks** in the sidebar. Home and Holdings fill in "
            "when the job completes (usually seconds from the shared S&P library)."
        ),
        sidebar_hint="Portfolio is loading in the background — check **Background tasks**.",
    ),
    OnboardingStep(
        id="live_reload",
        title="Reload live data (recommended)",
        detail=(
            "Click **Reload live data** in the sidebar for today's prices, yield charts, "
            "and risk watchlists. This also runs in the background (~1–2 min for many holdings)."
        ),
        sidebar_hint="Click **Reload live data** for fresh prices and yield charts.",
    ),
    OnboardingStep(
        id="explore",
        title="Explore your workspace",
        detail=(
            "On **Home**, review the positions table (click a ticker for full analysis). "
            "Use the section buttons for **Holdings**, **Dividend income**, and "
            "**Deposits & benchmarks**. "
            "You can research any S&P 500 name above the table before adding it."
        ),
        sidebar_hint=(
            "Use the section buttons on Home — start with **Holdings** or **Dividend income**."
        ),
    ),
)

DEMO_ONBOARDING_STEPS: tuple[OnboardingStep, ...] = (
    OnboardingStep(
        id="load_demo",
        title="Load the demo portfolio",
        detail="Click **Load demo portfolio** — sample holdings KO, JNJ, and O load instantly.",
        sidebar_hint="Load the demo portfolio from Home.",
    ),
    OnboardingStep(
        id="try_examples",
        title="Try the guided examples",
        detail="Open **Try it — 3 quick examples** on Home to jump to analysis and income views.",
        sidebar_hint="Expand **Try it — 3 quick examples** on Home.",
    ),
    OnboardingStep(
        id="live_reload",
        title="Reload live data",
        detail=(
            "Use **Reload live data** in the sidebar to refresh prices and charts "
            "in the background."
        ),
        sidebar_hint="Click **Reload live data** in the sidebar.",
    ),
)


def _session_get(session: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return session.get(key, default)
    except AttributeError:
        return default


def is_step_complete(
    step_id: str,
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,  # noqa: ARG001
) -> bool:
    """Return True when an onboarding step is satisfied."""
    if step_id == "add_holding":
        return has_holdings
    if step_id == "background_load":
        return bool(_session_get(session, "portfolio_details_rows"))
    if step_id == "live_reload":
        return bool(_session_get(session, "portfolio_analysis_ready")) or bool(
            _session_get(session, ONBOARDING_LIVE_RELOAD_KEY)
        )
    if step_id == "explore":
        return bool(_session_get(session, "portfolio_analysis_ready")) and bool(
            _session_get(session, "portfolio_details_rows")
        )
    if step_id == "load_demo":
        return bool(_session_get(session, "portfolio_details_rows"))
    if step_id == "try_examples":
        return bool(_session_get(session, "portfolio_show_examples"))
    return False


def onboarding_steps(*, is_demo: bool) -> Sequence[OnboardingStep]:
    return DEMO_ONBOARDING_STEPS if is_demo else REAL_USER_ONBOARDING_STEPS


def step_progress(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
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
            ),
        )
        for step in steps
    ]


def onboarding_complete(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
) -> bool:
    progress = step_progress(has_holdings=has_holdings, session=session, is_demo=is_demo)
    return bool(progress) and all(done for _, done in progress)


def should_show_onboarding(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
) -> bool:
    if _session_get(session, ONBOARDING_DISMISSED_KEY):
        return False
    return not onboarding_complete(
        has_holdings=has_holdings,
        session=session,
        is_demo=is_demo,
    )


def current_sidebar_hint(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
) -> str | None:
    if not should_show_onboarding(has_holdings=has_holdings, session=session, is_demo=is_demo):
        return None
    for step, done in step_progress(
        has_holdings=has_holdings,
        session=session,
        is_demo=is_demo,
    ):
        if not done:
            return step.sidebar_hint
    return None


def completed_step_count(
    *,
    has_holdings: bool,
    session: Mapping[str, Any],
    is_demo: bool = False,
) -> tuple[int, int]:
    progress = step_progress(has_holdings=has_holdings, session=session, is_demo=is_demo)
    done = sum(1 for _, complete in progress if complete)
    return done, len(progress)
