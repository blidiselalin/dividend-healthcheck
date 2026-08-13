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
    render_beta_badge,
    render_data_provenance,
    render_demo_progress,
    render_feature_cards,
    render_html,
    render_info_panel,
    render_logo,
    render_metric_strip,
    render_page_divider,
    render_section_header,
    render_trust_list,
)
from ui.theme import inject_command_center_theme

AUTH_REQUESTED_KEY = "command_center_auth_requested"  # legacy; AUTH view supersedes
CC_RETURN_VIEW_KEY = "command_center_return_view"
CC_RETURN_PAGE_KEY = "command_center_return_page"
_ANALYTICS_LAST_KEY = "command_center_last_analytics"

_CC_CSS = """
<style>
[data-testid="stMain"] [data-testid="block-container"] {
  max-width: var(--ds-content-width) !important;
  padding-left: var(--ds-space-4) !important;
  padding-right: var(--ds-space-4) !important;
}
@media (max-width: 640px) {
  .cc-hero-title { font-size: clamp(1.45rem, 7vw, 1.9rem) !important; }
  .cc-preview-card .ds-metric-grid,
  .cc-preview-card + div .ds-metric-grid {
    grid-template-columns: 1fr !important;
  }
  .ds-demo-progress { gap: var(--ds-space-1) !important; }
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


@dataclass(frozen=True)
class PublicRoute:
    view: PublicView
    demo_page: DemoPage


_VALID_VIEWS = frozenset(v.value for v in PublicView)
_VALID_PAGES = frozenset(p.value for p in DemoPage)

_PRODUCT_JOURNEY_STEPS = (
    "Import or add",
    "Verify",
    "Received income",
    "Estimated income",
    "Risks",
    "Research",
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


def render_public_navigation(route: PublicRoute) -> None:
    top_l, top_m, top_r = st.columns([2.2, 2.6, 1.1], gap="small")
    with top_l:
        render_logo(tagline="Product · interactive demo")
    with top_m:
        c1, c2, c3 = st.columns(3)
        with c1:
            product_on = route.view == PublicView.PRODUCT
            st.button(
                "Product · active" if product_on else "Product",
                key="cc_nav_product",
                use_container_width=True,
                type="primary" if product_on else "secondary",
                disabled=product_on,
                on_click=navigate_public,
                args=(PublicView.PRODUCT, DemoPage.OVERVIEW),
                kwargs={"source_section": "nav"},
            )
        with c2:
            demo_on = route.view == PublicView.DEMO
            st.button(
                "Interactive demo · active" if demo_on else "Interactive demo",
                key="cc_nav_demo",
                use_container_width=True,
                type="primary" if demo_on else "secondary",
                disabled=demo_on,
                on_click=navigate_public,
                args=(PublicView.DEMO, DemoPage.OVERVIEW),
                kwargs={
                    "source_section": "nav",
                    "analytics_event": "public_demo_started",
                    "analytics_dedupe_key": "started",
                },
            )
        with c3:
            auth_on = route.view == PublicView.AUTH
            st.button(
                "Create portfolio · active" if auth_on else "Create portfolio",
                key="cc_nav_auth",
                use_container_width=True,
                type="primary" if auth_on else "secondary",
                disabled=auth_on,
                on_click=navigate_to_auth,
                kwargs={"source_section": "nav"},
            )
    with top_r:
        from ui.theme_mode import render_theme_toggle

        render_theme_toggle()


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
            '<p class="cc-hero-kicker">Dividend command center</p>'
            '<h1 class="cc-hero-title">Dividend income you can explain.</h1>'
            '<p class="cc-hero-sub">'
            "Track what was paid, understand what may be at risk, and estimate what comes next."
            "</p>"
            "</div>"
        )
        st.button(
            "Explore the interactive demo",
            type="primary",
            use_container_width=True,
            key="cc_hero_demo",
            on_click=navigate_public,
            args=(PublicView.DEMO, DemoPage.OVERVIEW),
            kwargs={
                "source_section": "hero",
                "analytics_event": "public_demo_started",
                "analytics_dedupe_key": "started",
            },
        )
    with right:
        holding_count = len(dashboard.holdings)
        render_html(
            f'<div class="cc-preview-card" aria-label="Sample portfolio preview">'
            f'<p class="cc-preview-label">Live sample summary · {holding_count} holdings</p>'
            f"</div>"
        )
        render_metric_strip(
            [
                (
                    "Estimated annual income",
                    f"${dashboard.annual_income_usd:,.2f}",
                    "Estimated",
                    True,
                ),
                ("Monthly income average", f"${monthly_avg:,.2f}", "Estimated"),
                ("Portfolio yield", yield_label, "Estimated"),
                (
                    "Sample holdings",
                    str(holding_count),
                    "KO, JNJ, O by default",
                ),
            ]
        )
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
        "The income story brokers leave incomplete",
        "Educational framing — not investment advice.",
    )
    render_feature_cards(
        [
            (
                "01",
                "Broker reports",
                "Explain transactions, not the complete dividend income story.",
            ),
            (
                "02",
                "Mixed totals",
                "Portfolio trackers often blend received and projected dividends.",
            ),
            (
                "03",
                "Yield alone",
                "High yield does not explain payout safety or concentration risk.",
            ),
        ]
    )
    render_page_divider()

    render_section_header("How DividendScope works", "Track · Analyze · Forecast")
    render_feature_cards(
        [
            ("Track", "Track", "Received dividends, transactions, and holdings."),
            ("Analyze", "Analyze", "Payout safety, concentration, and dividend trends."),
            ("Forecast", "Forecast", "Upcoming payments and estimated annual income."),
        ]
    )
    render_page_divider()

    render_section_header(
        "Your first session",
        "Import an IBKR activity statement or add holdings manually.",
    )
    render_demo_progress(list(_PRODUCT_JOURNEY_STEPS), active_index=0)
    render_info_panel(
        "Use **Explore the interactive demo** above to try sample holdings, then "
        "create an account when you are ready to import your own data."
    )
    render_page_divider()

    render_section_header("Built for private portfolios", "Trust by design")
    render_trust_list(
        [
            "Private user portfolios in PostgreSQL",
            "Shared public market-data library",
            "Transparent dividend and scoring terminology",
            "Received and estimated income kept separate",
            "Self-hostable deployment",
            "Educational use only — not financial advice",
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
    st.button(
        "← Back to previous page",
        key="cc_auth_return",
        use_container_width=True,
        on_click=return_from_auth,
    )
    with st.container(border=True):
        st.info(
            "Create an account here — Google sign-up and the demo portfolio stay available. "
            "Guest holdings are not written to the database until you sign up."
        )
        auth_block()
    st.link_button(
        "View project on GitHub",
        "https://github.com/blidiselalin/dividend-healthcheck",
        use_container_width=True,
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

    render_public_navigation(route)

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
