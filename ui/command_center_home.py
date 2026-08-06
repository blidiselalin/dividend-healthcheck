"""
Pre-login Dividend Command Center — Product landing + Interactive demo router.

Public page: Product / Demo navigation via query params. Guest holdings stay in session.
"""

from __future__ import annotations

import html as html_module
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
    render_feature_cards,
    render_html,
    render_logo,
    render_metric_grid,
    render_page_divider,
    render_section_header,
)
from ui.theme import inject_command_center_theme

AUTH_REQUESTED_KEY = "command_center_auth_requested"
_ANALYTICS_LAST_KEY = "command_center_last_analytics"

_CC_CSS = """
<style>
[data-testid="stMain"] [data-testid="block-container"] {
  max-width: 1080px !important;
  padding-left: 1rem !important;
  padding-right: 1rem !important;
}
@media (max-width: 640px) {
  .cc-hero-title { font-size: clamp(1.4rem, 6.5vw, 1.85rem) !important; }
  .cc-preview-card .ds-metric-grid { grid-template-columns: 1fr !important; }
}
</style>
"""


class PublicView(StrEnum):
    PRODUCT = "product"
    DEMO = "demo"


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

    return PublicRoute(view=PublicView.PRODUCT, demo_page=DemoPage.OVERVIEW)


def apply_public_route(route: PublicRoute) -> None:
    """Update only view/page query keys (preserve unrelated params)."""
    st.query_params["view"] = route.view.value
    st.query_params["page"] = route.demo_page.value


def request_auth_panel(*, source_section: str) -> None:
    st.session_state[AUTH_REQUESTED_KEY] = True
    track_guidance_event(
        "public_create_portfolio_clicked",
        session=st.session_state,
        properties={"source_section": source_section},
    )


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


def render_public_navigation(route: PublicRoute) -> None:
    top_l, top_m, top_r = st.columns([2.2, 2.6, 1.1], gap="small")
    with top_l:
        render_logo(tagline="Product · interactive demo")
    with top_m:
        product_on = route.view == PublicView.PRODUCT
        c1, c2 = st.columns(2)
        with c1:
            label = "Product · active" if product_on else "Product"
            if st.button(
                label,
                key="cc_nav_product",
                use_container_width=True,
                type="primary" if product_on else "secondary",
            ):
                apply_public_route(PublicRoute(PublicView.PRODUCT, DemoPage.OVERVIEW))
                st.rerun()
        with c2:
            label = "Interactive demo" if product_on else "Interactive demo · active"
            if st.button(
                label,
                key="cc_nav_demo",
                use_container_width=True,
                type="secondary" if product_on else "primary",
            ):
                _track_once(
                    "public_demo_started",
                    dedupe_key="started",
                    properties={"source_section": "nav"},
                )
                apply_public_route(PublicRoute(PublicView.DEMO, DemoPage.OVERVIEW))
                st.rerun()
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
            '<h1 class="cc-hero-title">Dividend income you can explain.</h1>'
            '<p class="cc-hero-sub">'
            "Track what was paid, understand what may be at risk, and estimate what comes next."
            "</p>"
        )
        a1, a2 = st.columns(2)
        with a1:
            if st.button(
                "Explore the interactive demo",
                type="primary",
                use_container_width=True,
                key="cc_hero_demo",
            ):
                _track_once(
                    "public_demo_started",
                    dedupe_key="started",
                    properties={"source_section": "hero"},
                )
                apply_public_route(PublicRoute(PublicView.DEMO, DemoPage.OVERVIEW))
                st.rerun()
        with a2:
            if st.button(
                "Create your portfolio",
                use_container_width=True,
                key="cc_hero_auth",
            ):
                request_auth_panel(source_section="hero")
                st.rerun()
    with right:
        holding_count = len(dashboard.holdings)
        render_html(
            f'<div class="cc-preview-card" aria-label="Sample portfolio preview">'
            f'<p class="cc-preview-label">Live sample summary · {holding_count} holdings</p>'
            f"</div>"
        )
        render_metric_grid(
            [
                (
                    "Estimated annual income",
                    f"${dashboard.annual_income_usd:,.2f}",
                    "Estimated",
                    True,
                ),
                ("Monthly income average", f"${monthly_avg:,.2f}", "Estimated"),
                ("Portfolio yield", html_module.escape(yield_label), "Estimated"),
                (
                    "Sample holdings",
                    str(holding_count),
                    "KO, JNJ, O by default",
                ),
            ]
        )


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
    st.markdown(
        """
1. Import an IBKR activity statement or add holdings manually.
2. Review imported holdings and dividend transactions.
3. Resolve warnings or reconciliation differences.
4. Explore income, risk, and research.
"""
    )
    if st.button("Try the interactive demo", key="cc_journey_demo", use_container_width=True):
        apply_public_route(PublicRoute(PublicView.DEMO, DemoPage.IMPORT))
        st.rerun()
    render_page_divider()

    render_section_header("Built for private portfolios", "Trust by design")
    st.markdown(
        """
- Private user portfolios in PostgreSQL
- Shared public market-data library
- Transparent dividend and scoring terminology
- Received and estimated income kept separate
- Self-hostable deployment
- Educational use only — not financial advice
"""
    )


def render_public_conversion_panel(*, auth_block: Callable[[], None]) -> None:
    """Single authentication panel — auth_block widgets have fixed keys."""
    highlighted = bool(st.session_state.get(AUTH_REQUESTED_KEY))
    render_page_divider()
    render_section_header(
        "Create your portfolio",
        "Your sample try-list holdings can transfer after you create an account.",
    )
    render_research_disclaimer(compact=True)
    with st.container(border=highlighted):
        if highlighted:
            st.info("Create an account here — Google sign-up and demo portfolio stay available.")
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

    guest = guest_holdings_from_session(st.session_state)
    dashboard = build_guest_dashboard(guest)

    render_public_navigation(route)

    if route.view == PublicView.DEMO:
        from ui.command_center_demo import render_public_demo

        render_public_demo(route=route, dashboard=dashboard)
    else:
        render_public_product_page(dashboard=dashboard)

    render_public_conversion_panel(auth_block=auth_block)
