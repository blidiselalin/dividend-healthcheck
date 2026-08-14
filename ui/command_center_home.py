"""
Pre-login Dividend Command Center — Product / Interactive demo / Auth router.

Public page: Product / Demo / Auth navigation via query params. Guest holdings stay in session.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import streamlit as st

from services.guest_playground import (
    GuestDashboard,
    build_guest_dashboard,
    guest_holdings_from_session,
)
from services.guidance_analytics import track_guidance_event
from ui.beta_disclaimer import render_research_disclaimer
from ui.design_system import (
    PRODUCT_NAME,
    render_attention_list,
    render_beta_badge,
    render_data_provenance,
    render_demo_progress,
    render_feature_cards,
    render_html,
    render_info_panel,
    render_logo,
    render_metric_strip,
    render_page_divider,
    render_proof_pills,
    render_section_header,
    render_story_cards,
)
from ui.theme import inject_command_center_theme

AUTH_REQUESTED_KEY = "command_center_auth_requested"  # legacy; AUTH view supersedes
CC_RETURN_VIEW_KEY = "command_center_return_view"
CC_RETURN_PAGE_KEY = "command_center_return_page"
CC_FEEDBACK_KEY = "cc_public_feedback"
PUBLIC_SHELL_KEY = "cc_public_shell"
_ANALYTICS_LAST_KEY = "command_center_last_analytics"

_CC_CSS = """
<style>
[data-testid="stMain"] [data-testid="block-container"] {
  max-width: var(--ds-content-width) !important;
  padding-left: var(--ds-space-4) !important;
  padding-right: var(--ds-space-4) !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_"] button,
.st-key-cc_public_shell [class*="st-key-cc_btn_"] [data-testid="stLinkButton"] a {
  min-height: 44px !important;
  border-radius: 10px !important;
  font-weight: 700 !important;
  white-space: normal !important;
  line-height: 1.25 !important;
  letter-spacing: -0.01em !important;
  padding: 0.45rem 0.85rem !important;
  overflow-wrap: anywhere;
  transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease,
    transform 0.16s ease, opacity 0.16s ease !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_"] button:focus-visible,
.st-key-cc_public_shell [class*="st-key-cc_btn_"] [data-testid="stLinkButton"] a:focus-visible {
  outline: 3px solid rgba(45, 212, 191, 0.45) !important;
  outline-offset: 2px !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_"] button:active:not(:disabled) {
  transform: translateY(1px) !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_ghost_"] button,
.st-key-cc_public_shell [class*="st-key-cc_btn_ghost_"] [data-testid="stLinkButton"] a {
  background: transparent !important;
  border: 1px solid var(--ds-border) !important;
  color: var(--ds-text) !important;
  box-shadow: none !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_ghost_"] button:hover:not(:disabled),
.st-key-cc_public_shell [class*="st-key-cc_btn_ghost_"] [data-testid="stLinkButton"] a:hover {
  background: var(--ds-surface-elevated) !important;
  border-color: var(--ds-highlight-border) !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_tab_"] button {
  background: var(--ds-surface) !important;
  border: 1px solid var(--ds-border) !important;
  color: var(--ds-text) !important;
  box-shadow: none !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_tab_"] button:hover:not(:disabled) {
  border-color: var(--ds-highlight-border) !important;
  background: var(--ds-surface-highlight) !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_tab_"] button:disabled,
.st-key-cc_public_shell [class*="st-key-cc_btn_tab_"] button[kind="primary"]:disabled,
.st-key-cc_public_shell .st-key-cc_header_cta button:disabled {
  opacity: 1 !important;
  filter: none !important;
  color: var(--ds-btn-primary-text, #042f2e) !important;
  background: linear-gradient(135deg, var(--ds-primary-light) 0%, var(--ds-primary) 100%) !important;
  border-color: transparent !important;
  box-shadow: var(--ds-btn-shadow, 0 8px 24px rgba(45, 212, 191, 0.18)) !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_danger_"] button {
  background: rgba(248, 113, 113, 0.12) !important;
  border: 1px solid rgba(248, 113, 113, 0.45) !important;
  color: #fecaca !important;
}
.st-key-cc_public_shell [class*="st-key-cc_btn_danger_"] button:hover:not(:disabled) {
  background: rgba(248, 113, 113, 0.22) !important;
  border-color: #f87171 !important;
}
.st-key-cc_public_shell .st-key-cc_auth_providers button {
  min-height: 44px !important;
  border-radius: 10px !important;
  font-weight: 700 !important;
}
@media (max-width: 640px) {
  .cc-hero-title { font-size: clamp(1.45rem, 7vw, 1.9rem) !important; }
  .cc-preview-card .ds-metric-grid,
  .cc-preview-card + div .ds-metric-grid {
    grid-template-columns: 1fr !important;
  }
  .ds-demo-progress { gap: var(--ds-space-1) !important; }
  .st-key-cc_public_shell .st-key-cc_header_bar [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
  }
  .st-key-cc_public_shell .st-key-cc_header_tabs [data-testid="stHorizontalBlock"],
  .st-key-cc_public_shell .st-key-cc_demo_nav_primary [data-testid="stHorizontalBlock"],
  .st-key-cc_public_shell .st-key-cc_demo_nav_optional [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
  }
  .st-key-cc_public_shell .st-key-cc_header_cta {
    flex: 1 1 100% !important;
    width: 100% !important;
    min-width: 100% !important;
  }
  .st-key-cc_public_shell .st-key-cc_hero_actions [data-testid="stHorizontalBlock"],
  .st-key-cc_public_shell .st-key-cc_holdings_add [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
  }
  .st-key-cc_public_shell .st-key-cc_hero_actions [data-testid="stHorizontalBlock"] > div,
  .st-key-cc_public_shell .st-key-cc_holdings_add [data-testid="stHorizontalBlock"] > div {
    width: 100% !important;
    min-width: 0 !important;
  }
}
@media (max-width: 390px) {
  .st-key-cc_public_shell { overflow-x: hidden; }
}
</style>
"""


class PublicView(StrEnum):
    PRODUCT = "product"
    DEMO = "demo"
    AUTH = "auth"


class DemoPage(StrEnum):
    OVERVIEW = "overview"
    INCOME = "income"
    RISK = "risk"
    RESEARCH = "research"
    IMPORT = "import"


class PublicButtonVariant(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    GHOST = "ghost"
    TAB = "tab"
    DANGER = "danger"


@dataclass(frozen=True)
class PublicRoute:
    view: PublicView
    demo_page: DemoPage


_VALID_VIEWS = frozenset(v.value for v in PublicView)
_VALID_PAGES = frozenset(p.value for p in DemoPage)

_PRODUCT_JOURNEY_STEPS = (
    "Add or import",
    "Validate",
    "Reconcile",
    "Review next",
)


def _first_param(params: Mapping[str, object], key: str) -> str:
    raw = params.get(key)
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        return str(raw[0] if raw else "").strip().lower()
    return str(raw).strip().lower()


def resolve_public_route(params: Mapping[str, object]) -> PublicRoute:
    """Validate untrusted query params; invalid values fall back safely."""
    view_raw = _first_param(params, "view")
    page_raw = _first_param(params, "page")

    if view_raw not in _VALID_VIEWS:
        return PublicRoute(view=PublicView.PRODUCT, demo_page=DemoPage.OVERVIEW)

    view = PublicView(view_raw)
    if view == PublicView.DEMO:
        page = DemoPage(page_raw) if page_raw in _VALID_PAGES else DemoPage.OVERVIEW
        return PublicRoute(view=PublicView.DEMO, demo_page=page)

    if view == PublicView.AUTH:
        return PublicRoute(view=PublicView.AUTH, demo_page=DemoPage.OVERVIEW)

    return PublicRoute(view=PublicView.PRODUCT, demo_page=DemoPage.OVERVIEW)


def apply_public_route(route: PublicRoute) -> None:
    """Update only view/page query keys (preserve unrelated params)."""
    st.query_params["view"] = route.view.value
    st.query_params["page"] = route.demo_page.value


def _track_once(
    event_name: str, *, dedupe_key: str, properties: dict[str, Any] | None = None
) -> None:
    last = st.session_state.setdefault(_ANALYTICS_LAST_KEY, {})
    if not isinstance(last, dict):
        last = {}
        st.session_state[_ANALYTICS_LAST_KEY] = last
    if last.get(event_name) == dedupe_key:
        return
    last[event_name] = dedupe_key
    track_guidance_event(event_name, session=st.session_state, properties=properties)


def navigate_public(
    view: str | PublicView,
    page: str | DemoPage = DemoPage.OVERVIEW,
    *,
    source_section: str | None = None,
    analytics_event: str | None = None,
    analytics_dedupe_key: str | None = None,
) -> None:
    """
    Central navigation callback for public Product / Demo / Auth routes.

    Intended for ``st.button(..., on_click=...)`` — Streamlit reruns after the callback.
    Do not call ``st.rerun()`` here.
    """
    view_value = view.value if isinstance(view, PublicView) else str(view)
    page_value = page.value if isinstance(page, DemoPage) else str(page)
    route = resolve_public_route({"view": view_value, "page": page_value})
    if analytics_event:
        props: dict[str, Any] = {}
        if source_section:
            props["source_section"] = source_section
        if route.view == PublicView.DEMO:
            props["demo_page"] = route.demo_page.value
        _track_once(
            analytics_event,
            dedupe_key=analytics_dedupe_key or f"{route.view.value}:{route.demo_page.value}",
            properties=props or None,
        )
    apply_public_route(route)


def navigate_to_auth(*, source_section: str) -> None:
    """Open the dedicated auth route and remember where the user came from."""
    current = resolve_public_route(dict(st.query_params))
    if current.view != PublicView.AUTH:
        st.session_state[CC_RETURN_VIEW_KEY] = current.view.value
        st.session_state[CC_RETURN_PAGE_KEY] = current.demo_page.value
    st.session_state[AUTH_REQUESTED_KEY] = True
    track_guidance_event(
        "public_create_portfolio_clicked",
        session=st.session_state,
        properties={"source_section": source_section},
    )
    apply_public_route(PublicRoute(PublicView.AUTH, DemoPage.OVERVIEW))


def return_from_auth() -> None:
    """Restore the page the user left when opening Create portfolio."""
    view_raw = str(st.session_state.get(CC_RETURN_VIEW_KEY) or PublicView.DEMO.value)
    page_raw = str(st.session_state.get(CC_RETURN_PAGE_KEY) or DemoPage.OVERVIEW.value)
    route = resolve_public_route({"view": view_raw, "page": page_raw})
    if route.view == PublicView.AUTH:
        route = PublicRoute(PublicView.DEMO, DemoPage.OVERVIEW)
    apply_public_route(route)


# Back-compat alias used by older call sites / tests.
def request_auth_panel(*, source_section: str) -> None:
    navigate_to_auth(source_section=source_section)


def set_public_feedback(kind: str, message: str, source: str) -> None:
    """Store one public-page result until the next mutation replaces it."""
    st.session_state[CC_FEEDBACK_KEY] = {
        "kind": kind,
        "message": message,
        "source": source,
    }


def render_public_feedback() -> None:
    payload = st.session_state.get(CC_FEEDBACK_KEY)
    if not isinstance(payload, dict):
        return
    message = str(payload.get("message") or "").strip()
    if not message:
        return
    kind = str(payload.get("kind") or "info")
    renderer = {
        "success": st.success,
        "info": st.info,
        "warning": st.warning,
        "error": st.error,
    }.get(kind, st.info)
    renderer(message)


def render_public_button(
    label: str,
    *,
    key: str,
    variant: PublicButtonVariant = PublicButtonVariant.SECONDARY,
    on_click: Callable[..., Any] | None = None,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    disabled: bool = False,
    selected: bool = False,
    use_container_width: bool = True,
    help: str | None = None,
    url: str | None = None,
    submit: bool = False,
) -> bool:
    """Native Streamlit button wrapped for public-shell CSS variants."""
    wrap_key = f"cc_btn_{variant.value}_{key}"
    streamlit_type = (
        "primary" if variant == PublicButtonVariant.PRIMARY or selected else "secondary"
    )
    click_kwargs = kwargs or {}
    with st.container(key=wrap_key):
        if url:
            st.link_button(
                label,
                url,
                use_container_width=use_container_width,
                type=streamlit_type,
                help=help,
            )
            return False
        if submit:
            return bool(
                st.form_submit_button(
                    label,
                    type=streamlit_type,
                    use_container_width=use_container_width,
                    help=help,
                    on_click=on_click,
                    args=args,
                    kwargs=click_kwargs,
                )
            )
        return bool(
            st.button(
                label,
                key=key,
                type=streamlit_type,
                use_container_width=use_container_width,
                disabled=disabled or selected,
                help=help,
                on_click=on_click,
                args=args,
                kwargs=click_kwargs,
            )
        )


def render_public_navigation(route: PublicRoute) -> None:
    with st.container(key="cc_header_bar"):
        logo_col, tabs_col, theme_col, cta_col = st.columns([1.7, 2.4, 1.0, 1.5], gap="small")
        with logo_col:
            render_logo(tagline="Product · interactive demo")
        with tabs_col, st.container(key="cc_header_tabs"):
            t1, t2 = st.columns(2)
            with t1:
                product_on = route.view == PublicView.PRODUCT
                render_public_button(
                    "Product",
                    key="cc_nav_product",
                    variant=PublicButtonVariant.TAB,
                    selected=product_on,
                    on_click=navigate_public,
                    args=(PublicView.PRODUCT, DemoPage.OVERVIEW),
                    kwargs={"source_section": "nav"},
                )
            with t2:
                demo_on = route.view == PublicView.DEMO
                render_public_button(
                    "Interactive demo",
                    key="cc_nav_demo",
                    variant=PublicButtonVariant.TAB,
                    selected=demo_on,
                    on_click=navigate_public,
                    args=(PublicView.DEMO, DemoPage.OVERVIEW),
                    kwargs={
                        "source_section": "nav",
                        "analytics_event": "public_demo_started",
                        "analytics_dedupe_key": "started",
                    },
                )
        with theme_col:
            from ui.theme_mode import render_theme_toggle

            render_theme_toggle()
        with cta_col, st.container(key="cc_header_cta"):
            auth_on = route.view == PublicView.AUTH
            render_public_button(
                "Create portfolio",
                key="cc_nav_auth",
                variant=PublicButtonVariant.PRIMARY,
                selected=auth_on,
                on_click=navigate_to_auth,
                kwargs={"source_section": "nav"},
            )


def _spark_bars(dashboard: GuestDashboard) -> str:
    values = [float(value) for _, value in dashboard.monthly_forecast[:12]]
    peak = max(values) if values else 0.0
    if peak <= 0:
        return ""
    bars = "".join(
        f'<span class="cc-spark-bar" style="height:{max(10, int(value / peak * 100))}%"></span>'
        for value in values
    )
    return f'<div class="cc-sparkline" aria-hidden="true">{bars}</div>'


def guest_attention_items(dashboard: GuestDashboard) -> list[tuple[str, str, str, str]]:
    """Sample attention rows for Product preview and Demo overview/risk."""
    alerts = {alert.symbol: alert for alert in dashboard.safety_alerts}
    items: list[tuple[str, str, str, str]] = []
    for holding in dashboard.holdings:
        alert = alerts.get(holding.symbol)
        company = holding.company_name or holding.symbol
        if alert is None:
            items.append((holding.symbol, company, "No blocking sample signal.", "Healthy"))
            continue
        severity = (alert.severity or "").strip().lower()
        if severity in {"high", "risky"}:
            status = "Needs attention"
        elif severity in {"medium", "watch"}:
            status = "Review"
        else:
            status = "Healthy"
        items.append((holding.symbol, company, alert.message, status))
    rank = {"Needs attention": 0, "Review": 1, "Healthy": 2}
    items.sort(key=lambda row: rank.get(row[3], 9))
    return items


def _render_hero(dashboard: GuestDashboard) -> None:
    monthly_avg = dashboard.annual_income_usd / 12 if dashboard.annual_income_usd else 0.0
    yield_label = (
        f"{dashboard.portfolio_yield_pct:.2f}%"
        if dashboard.portfolio_yield_pct is not None
        else "—"
    )
    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        render_beta_badge()
        render_html(
            '<div class="cc-hero">'
            '<p class="cc-hero-kicker">Beta launch experience</p>'
            '<h1 class="cc-hero-title">Your dividend portfolio, '
            '<span class="ds-accent">explained.</span></h1>'
            '<p class="cc-hero-sub">'
            "Reconcile what was paid, surface what needs attention, and forecast "
            "the next twelve months — in one private investor workspace."
            "</p>"
            "</div>"
        )
        with st.container(key="cc_hero_actions"):
            h1, h2 = st.columns(2)
            with h1:
                render_public_button(
                    "Try interactive demo",
                    key="cc_hero_demo",
                    variant=PublicButtonVariant.PRIMARY,
                    on_click=navigate_public,
                    args=(PublicView.DEMO, DemoPage.OVERVIEW),
                    kwargs={
                        "source_section": "hero",
                        "analytics_event": "public_demo_started",
                        "analytics_dedupe_key": "started",
                    },
                )
            with h2:
                render_public_button(
                    "Create portfolio",
                    key="cc_hero_auth",
                    variant=PublicButtonVariant.SECONDARY,
                    on_click=navigate_to_auth,
                    kwargs={"source_section": "hero"},
                )
        render_proof_pills(
            [
                "User-scoped portfolio data",
                "Income-first workflow",
                "Self-hostable",
                "No paid market-data key required",
            ]
        )
    with right:
        value = f"${dashboard.portfolio_value_usd:,.0f}"
        income = f"${dashboard.annual_income_usd:,.0f}"
        received = f"${dashboard.sample_received_gross_usd:,.0f}"
        render_html(
            '<div class="cc-window" aria-label="Illustrative DividendScope dashboard preview">'
            '<div class="cc-window-top"><span class="cc-window-dots" aria-hidden="true">'
            "<i></i><i></i><i></i></span>"
            "<span>DividendScope / portfolio command center</span></div>"
            "</div>"
        )
        render_metric_strip(
            [
                ("Portfolio value", value, "Illustrative prices"),
                ("Estimated 12 months", income, f"{yield_label} yield", True),
                ("Sample received", received, "Illustrative · not broker cash"),
                ("Monthly average", f"${monthly_avg:,.0f}", "Estimated"),
            ]
        )
        render_html(_spark_bars(dashboard))
        render_data_provenance(dashboard.provenance_label)


def render_public_product_page(*, dashboard: GuestDashboard) -> None:
    _track_once(
        "public_product_viewed",
        dedupe_key="product",
        properties={"source_section": "product"},
    )
    _render_hero(dashboard)
    render_page_divider()

    render_section_header(
        "Investors do not need more numbers. They need answers they can trust.",
        "Designed for the investor who has outgrown a spreadsheet but does not want a trading terminal.",
    )
    render_story_cards(
        [
            (
                "01 · Past",
                "What did I actually receive?",
                "Broker exports, taxes, and payment dates can make a simple total hard to verify.",
                "Answer: reconciled gross, tax, and net cash.",
            ),
            (
                "02 · Present",
                "Which income is becoming fragile?",
                "Yield alone does not explain payout coverage, concentration, or durability.",
                "Answer: prioritized, explainable risk signals.",
            ),
            (
                "03 · Future",
                "What should I expect next?",
                "Received and estimated income are often blended, weakening planning confidence.",
                "Answer: clearly labelled forward income.",
            ),
        ]
    )
    render_page_divider()

    render_section_header(
        "Three views. One continuous income story.",
        "Broker evidence, portfolio health, and forward expectations — with provenance on every number.",
    )
    render_feature_cards(
        [
            (
                "Received",
                "Cash evidence",
                "Gross dividends, withholding tax, and net receipts stay separate from estimates.",
            ),
            (
                "Health",
                "Portfolio attention",
                "See why a holding needs review — not a black-box buy or sell call.",
            ),
            (
                "Next",
                "Forward income",
                "A 12-month estimate you can challenge, labelled as estimated — not guaranteed cash.",
            ),
        ]
    )
    render_page_divider()

    render_section_header(
        "The first session ends with an understood portfolio.",
        "Every step has a clear completion state and a single next action.",
    )
    render_demo_progress(list(_PRODUCT_JOURNEY_STEPS), active_index=0)
    render_story_cards(
        [
            (
                "Step 1",
                "Add or import",
                "Start from sample holdings, or later from a supported IBKR activity statement.",
                "Outcome: a portfolio exists.",
            ),
            (
                "Step 2",
                "Validate",
                "Preview positions, dividends, and taxes before anything is treated as complete.",
                "Outcome: the import is understandable.",
            ),
            (
                "Step 3",
                "Reconcile",
                "Keep received cash distinct from estimated income so totals can be trusted.",
                "Outcome: the numbers are trusted.",
            ),
            (
                "Step 4",
                "Review next",
                "Open the one signal that matters now — then create a portfolio for your own data.",
                "Outcome: the aha moment.",
            ),
        ]
    )
    render_page_divider()

    render_section_header(
        "A focused operating system for dividend portfolios.",
        "The sample below uses the same guest holdings as the interactive demo.",
    )
    attention = guest_attention_items(dashboard)
    left, right = st.columns(2, gap="large")
    with left:
        render_metric_strip(
            [
                (
                    "Portfolio value",
                    f"${dashboard.portfolio_value_usd:,.0f}",
                    "Illustrative",
                ),
                (
                    "Estimated 12 months",
                    f"${dashboard.annual_income_usd:,.0f}",
                    "Estimated",
                    True,
                ),
                (
                    "Sample received",
                    f"${dashboard.sample_received_gross_usd:,.0f}",
                    "Illustrative",
                ),
                ("Holdings", str(len(dashboard.holdings)), "KO, JNJ, O by default"),
            ]
        )
        render_html(_spark_bars(dashboard))
        render_data_provenance("Live sample summary · same session as the interactive demo")
    with right:
        render_section_header("Attention, not alarm", "Signals explain what to inspect.")
        if attention:
            render_attention_list(attention)
        else:
            render_info_panel("No sample attention items for the current holdings.")
    render_page_divider()

    render_section_header(
        "Try the product story before you set up an account.",
        "Four actions in the interactive demo. Your sample list stays in this browser session.",
    )
    render_feature_cards(
        [
            ("1", "Adjust holdings", "Change sample shares and watch estimated income update."),
            ("2", "Separate cash", "See received-style totals beside the 12-month estimate."),
            ("3", "Inspect a signal", "Read the reason behind the highest-priority review item."),
            (
                "4",
                "Optional research",
                "Open evidence for one holding, or load a packaged IBKR sample.",
            ),
        ]
    )
    render_info_panel(
        "Use **Try interactive demo** above when you are ready. "
        "Create a portfolio from the header to import your own statement."
    )
    render_page_divider()

    render_section_header(
        "Financial data must be explainable before it is beautiful.",
        "Provenance, reconciliation, and transparent labels — educational use only.",
    )
    render_story_cards(
        [
            (
                "Provenance",
                "Visible data sources",
                "Received cash points at broker imports. Market library data stays distinct from holdings you enter.",
                "Broker evidence · market sources · user input",
            ),
            (
                "Reconciliation",
                "An import is not done when rows parse",
                "Positions, dividends, taxes, and duplicates get explicit checks before the portfolio is trusted.",
                "Preview · apply · review issues",
            ),
            (
                "Labels",
                "No blended certainty",
                "Received, accrued, declared, and estimated values stay visually separate.",
                "Received · accrued · estimated",
            ),
            (
                "Privacy",
                "Private, bounded positioning",
                "User portfolios are scoped to the account. Research aids — not personalized advice.",
                "Google sign-up · PostgreSQL · self-hostable",
            ),
        ]
    )


def render_public_auth_page(*, auth_block: Callable[[], None]) -> None:
    """Dedicated Create portfolio / sign-up route — guest holdings stay in session."""
    _track_once(
        "public_auth_viewed",
        dedupe_key="auth",
        properties={"source_section": "auth"},
    )
    render_section_header(
        "Create your portfolio",
        "Your sample try-list holdings stay in this browser session and can transfer after sign-up.",
    )
    render_research_disclaimer(compact=True)
    render_public_button(
        "← Back to previous page",
        key="cc_auth_return",
        variant=PublicButtonVariant.GHOST,
        on_click=return_from_auth,
    )
    with st.container(border=True):
        st.info(
            "Create an account here — Google sign-up and the demo portfolio stay available. "
            "Guest holdings are not written to the database until you sign up."
        )
        with st.container(key="cc_auth_providers"):
            auth_block()
    render_public_button(
        "View project on GitHub",
        key="cc_auth_github",
        variant=PublicButtonVariant.GHOST,
        url="https://github.com/blidiselalin/dividend-healthcheck",
    )
    st.caption(f"{PRODUCT_NAME} · educational research only · not financial advice.")


def render_command_center_page(*, auth_block: Callable[[], None]) -> None:
    """Public experience router for the pre-login Command Center."""
    inject_command_center_theme()
    st.markdown(_CC_CSS, unsafe_allow_html=True)

    route = resolve_public_route(dict(st.query_params))
    # Normalize view/page when missing or invalid (preserve unrelated params).
    if (
        st.query_params.get("view") != route.view.value
        or st.query_params.get("page") != route.demo_page.value
    ):
        apply_public_route(route)
        st.rerun()

    with st.container(key=PUBLIC_SHELL_KEY):
        render_public_navigation(route)
        render_public_feedback()

        if route.view == PublicView.AUTH:
            render_public_auth_page(auth_block=auth_block)
            return

        guest = guest_holdings_from_session(st.session_state)
        dashboard = build_guest_dashboard(guest)

        if route.view == PublicView.DEMO:
            from ui.command_center_demo import render_public_demo

            render_public_demo(route=route, dashboard=dashboard)
        else:
            render_public_product_page(dashboard=dashboard)
