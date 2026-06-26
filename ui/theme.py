"""
Shared Streamlit theme — layout, navigation labels, and portfolio section map.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import streamlit as st

# Top-level app views (portfolio is home).
NAV_PORTFOLIO = "Portfolio"
NAV_SINGLE_STOCK = "Single stock"
NAV_DIVIDEND_KINGS = "Dividend Kings"
NAV_OPTIONS = [NAV_PORTFOLIO]

_LEGACY_NAV_MAP = {
    "Portfolio Details": NAV_PORTFOLIO,
    "All Dividend Kings": NAV_DIVIDEND_KINGS,
    "Single Stock": NAV_SINGLE_STOCK,
}

# Portfolio workspace sections: (sidebar label, internal key, one-line description).
PORTFOLIO_NAV: List[Tuple[str, str, str]] = [
    ("Home", "dashboard", "Snapshot, watchlists, and dividends paid this month"),
    ("Holdings", "holdings", "All positions — filter, explore, and compare"),
    ("Dividend income", "dividends", "Monthly calendar and net cash received after tax"),
    ("Dividend growth", "dividend_growth", "Dividend per share and year-over-year growth"),
    ("Purchase journal", "journal", "Buy dates, lots, and share counts"),
    ("Deposits & benchmarks", "deposits", "Monthly deposits, portfolio value, and index comparison"),
]

_LEGACY_PORTFOLIO_SECTION_LABELS = {
    "Overview": "Home",
    "Income": "Dividend income",
    "Growth": "Dividend growth",
    "Journal": "Purchase journal",
    "Deposits": "Deposits & benchmarks",
}

PORTFOLIO_SECTION_LABELS = [item[0] for item in PORTFOLIO_NAV]
PORTFOLIO_SECTION_BY_LABEL = {item[0]: item[1] for item in PORTFOLIO_NAV}
PORTFOLIO_HINT_BY_LABEL = {item[0]: item[2] for item in PORTFOLIO_NAV}
PORTFOLIO_LABEL_BY_KEY = {item[1]: item[0] for item in PORTFOLIO_NAV}

# Backward compatibility for older imports.
PORTFOLIO_SECTIONS = PORTFOLIO_SECTION_LABELS
PORTFOLIO_TAB_SCOPES = {
    key: (label, hint) for label, key, hint in PORTFOLIO_NAV
}


def normalize_nav_choice(value: str | None) -> str:
    if not value:
        return NAV_PORTFOLIO
    mapped = _LEGACY_NAV_MAP.get(value, value)
    if mapped in (NAV_SINGLE_STOCK, NAV_DIVIDEND_KINGS):
        return NAV_PORTFOLIO
    if mapped not in NAV_OPTIONS:
        return NAV_PORTFOLIO
    return mapped


def sidebar_heading(title: str) -> None:
    """Sidebar section title without Streamlit header anchors (avoids scroll clip)."""
    from ui.design_system import render_html

    render_html(f'<p class="ds-sidebar-heading">{title}</p>', sidebar=True)


def main_content_start() -> None:
    """Top spacer so the first main-panel message is not under the app toolbar."""
    from ui.design_system import render_html

    render_html('<div class="ds-main-top-spacer" aria-hidden="true"></div>')


def render_notice(message: str, *, kind: str = "info") -> None:
    """Full-width notice that wraps cleanly (no clipped alert text)."""
    from ui.design_system import render_html

    css_class = {
        "info": "ds-notice ds-notice-info",
        "success": "ds-notice ds-notice-success",
        "warning": "ds-notice ds-notice-warning",
    }.get(kind, "ds-notice ds-notice-info")
    render_html(f'<div class="{css_class}">{message}</div>')


def inject_command_center_theme() -> None:
    """Styles for the pre-login Dividend Command Center."""
    from ui.design_system import inject_design_system

    inject_design_system()


def inject_app_theme() -> None:
    from ui.design_system import inject_design_system

    inject_design_system()
    st.markdown(
        """
        <style>
        /* Hide Streamlit Cloud "Deploy" and developer menu (user-facing app). */
        [data-testid="stDeployButton"],
        .stAppDeployButton,
        [data-testid="stToolbarActions"] button[kind="header"],
        header a[href*="streamlit.io/cloud"] {
            display: none !important;
        }
        /* Main panel — room below Streamlit toolbar */
        [data-testid="stMain"] [data-testid="block-container"] {
            padding-top: 2rem !important;
            padding-bottom: 2rem;
            max-width: 1280px;
            scroll-padding-top: 2.5rem !important;
            overflow: visible !important;
        }
        .ds-main-top-spacer {
            display: block;
            height: 0.35rem;
            margin: 0;
            padding: 0;
        }
        [data-testid="stMain"] [data-testid="stVerticalBlock"],
        [data-testid="stMain"] [data-testid="stMarkdownContainer"] {
            overflow: visible !important;
        }
        /* Alerts and custom notices — full text visible */
        [data-testid="stAlert"],
        [data-testid="stAlert"] > div,
        [data-testid="stNotification"] {
            overflow: visible !important;
            white-space: normal !important;
            word-wrap: break-word !important;
        }
        [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
            line-height: 1.45 !important;
            margin: 0 !important;
        }
        .ds-notice {
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin: 0 0 1rem 0;
            line-height: 1.45;
            font-size: 0.92rem;
            overflow: visible;
            word-wrap: break-word;
        }
        .ds-notice-info {
            background: rgba(56, 189, 248, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.35);
            color: #bae6fd;
        }
        .ds-notice-success {
            background: rgba(52, 211, 153, 0.12);
            border: 1px solid rgba(52, 211, 153, 0.35);
            color: #a7f3d0;
        }
        .ds-notice-warning {
            background: rgba(251, 191, 36, 0.12);
            border: 1px solid rgba(251, 191, 36, 0.35);
            color: #fde68a;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] label p,
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] p {
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: unset !important;
        }
        .stButton button,
        [data-testid="stSelectbox"] label,
        [data-testid="stRadio"] label {
            white-space: normal !important;
        }
        /* Sidebar — scroll padding so top labels/messages are not cut off */
        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 3rem !important;
            padding-bottom: 2.5rem !important;
            scroll-padding-top: 3rem !important;
            overflow-y: auto !important;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"],
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] [data-testid="stAlert"] {
            overflow: visible !important;
        }
        p.ds-sidebar-heading {
            font-size: 1rem;
            font-weight: 600;
            color: #334155;
            line-height: 1.5;
            margin: 0.85rem 0 0.35rem 0;
            padding: 0;
        }
        [data-testid="stSidebar"] p.ds-sidebar-heading:first-of-type {
            margin-top: 0.15rem;
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            overflow: visible !important;
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            line-height: 1.4 !important;
            white-space: normal !important;
        }
        div[data-testid="stMetric"] {
            background: var(--ds-surface) !important;
            border: 1px solid var(--ds-border) !important;
            border-radius: 10px;
            padding: 0.55rem 0.75rem 0.45rem;
            min-height: 5.75rem;
            overflow: visible !important;
        }
        div[data-testid="stMetric"] label {
            font-size: 0.72rem;
            color: var(--ds-muted) !important;
            line-height: 1.35 !important;
            min-height: 2.4em;
            word-break: break-word;
            overflow-wrap: anywhere;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.15rem;
            font-weight: 600;
            color: var(--ds-text) !important;
            line-height: 1.25 !important;
            word-break: break-word;
        }
        div[data-testid="stMetricDelta"] {
            overflow: visible !important;
            white-space: normal !important;
            line-height: 1.3 !important;
            font-size: 0.78rem !important;
            word-break: break-word;
        }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] {
            gap: 0.75rem;
            align-items: stretch;
            flex-wrap: wrap;
        }
        [data-testid="stPlotlyChart"] {
            overflow: visible !important;
            margin-bottom: 0.75rem;
        }
        [data-testid="stPlotlyChart"] .js-plotly-plot {
            overflow: visible !important;
        }
        .ds-hero {
            background: linear-gradient(135deg, #134e4a 0%, #115e59 45%, #1a2740 100%);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
            border: 1px solid rgba(45, 212, 191, 0.2);
        }
        .ds-hero h2 {
            margin: 0 0 0.15rem 0;
            font-size: 1.35rem;
            font-weight: 650;
            color: #ffffff;
        }
        .ds-hero p {
            margin: 0;
            font-size: 0.9rem;
            color: #ecfdf5;
            opacity: 0.95;
        }
        .ds-hint {
            color: #64748b;
            font-size: 0.88rem;
            margin: 0 0 0.75rem 0;
        }
        [data-testid="stSegmentedControl"] {
            margin-bottom: 0.25rem;
        }
        .ds-portfolio-nav {
            margin: 0.5rem 0 1rem 0;
        }
        .ds-portfolio-nav-title {
            margin: 0 0 0.15rem 0;
            font-size: 1.05rem;
            font-weight: 650;
            color: var(--ds-text);
        }
        .ds-portfolio-nav-lead {
            margin: 0 0 0.85rem 0;
            color: var(--ds-muted);
            font-size: 0.88rem;
        }
        .ds-portfolio-nav-hint {
            color: var(--ds-muted);
            font-size: 0.8rem;
            line-height: 1.35;
            margin: 0.2rem 0 0.65rem 0;
            min-height: 2.4rem;
            word-break: break-word;
        }
        .ds-onboarding-sidebar-hint {
            font-size: 0.82rem;
            color: rgba(49, 51, 63, 0.85);
            background: rgba(28, 131, 225, 0.08);
            border-left: 3px solid rgba(28, 131, 225, 0.55);
            padding: 0.45rem 0.55rem;
            margin: 0 0 0.75rem 0;
            line-height: 1.4;
            border-radius: 0 4px 4px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.components.v1.html(
        """
        <script>
        (function () {
          const marker = "ds_streamlit_chunk_reload";
          function shouldReload(message) {
            if (!message) return false;
            return message.includes("Failed to fetch dynamically imported module")
              || message.includes("Importing a module script failed");
          }
          function reloadOnce() {
            if (sessionStorage.getItem(marker)) return;
            sessionStorage.setItem(marker, "1");
            window.location.reload();
          }
          window.addEventListener("error", function (event) {
            if (shouldReload(event.message || "")) reloadOnce();
          }, true);
          window.addEventListener("unhandledrejection", function (event) {
            const reason = event.reason;
            const message = typeof reason === "string"
              ? reason
              : (reason && reason.message) || "";
            if (shouldReload(message)) reloadOnce();
          });
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def render_page_header(*, title: str, subtitle: str, compact: bool = False) -> None:
    from ui.design_system import render_html, render_section_header

    if compact:
        render_section_header(title, subtitle)
        return
    render_html(f'<div class="ds-hero"><h2>{title}</h2><p>{subtitle}</p></div>')


def resolve_portfolio_section_label(label: str | None) -> str:
    """Normalize a section label to a known portfolio view name."""
    if not label:
        return "Home"
    mapped = _LEGACY_PORTFOLIO_SECTION_LABELS.get(label, label)
    if mapped not in PORTFOLIO_SECTION_LABELS:
        return "Home"
    return mapped


def portfolio_section_key_from_label(label: str | None) -> str:
    """Map a section label (or None) to the internal section key."""
    return PORTFOLIO_SECTION_BY_LABEL[resolve_portfolio_section_label(label)]


def current_portfolio_section_key() -> str:
    """Current section key from session state."""
    return portfolio_section_key_from_label(st.session_state.get("portfolio_section_label"))


def render_portfolio_section_nav() -> str:
    """Visible section picker — full list with descriptions. Returns internal section key."""
    active_label = resolve_portfolio_section_label(
        st.session_state.get("portfolio_section_label")
    )
    st.session_state["portfolio_section_label"] = active_label

    from ui.design_system import render_html

    render_html(
        '<div class="ds-portfolio-nav-section">'
        '<p class="ds-overline">Workspace</p>'
        '<p class="ds-portfolio-nav-title">Portfolio sections</p>'
        '<p class="ds-portfolio-nav-lead">'
        "Jump to a section — home, holdings, income, growth, journal, or deposits."
        "</p>"
        "</div>"
    )

    selected_label = active_label
    cols = st.columns(3)
    for index, (label, key, hint) in enumerate(PORTFOLIO_NAV):
        with cols[index % 3]:
            if st.button(
                label,
                key=f"portfolio_nav_{key}",
                use_container_width=True,
                type="primary" if label == active_label else "secondary",
                help=hint,
            ):
                selected_label = label
                st.session_state["portfolio_section_label"] = label
                st.rerun()
            render_html(f'<p class="ds-portfolio-nav-hint">{hint}</p>')

    st.session_state["portfolio_section_label"] = selected_label
    return PORTFOLIO_SECTION_BY_LABEL[selected_label]


def pick_portfolio_section() -> str:
    """Section picker — visible grid of all portfolio views. Returns internal section key."""
    return render_portfolio_section_nav()


def portfolio_data_ready() -> bool:
    """True when the UI may show holdings (demo session or real user with DB rows + cache)."""
    from services.portfolio_session import is_demo_session, user_has_holdings_in_db

    rows = bool(st.session_state.get("portfolio_details_rows"))
    if is_demo_session():
        return rows
    if not user_has_holdings_in_db():
        return False
    return rows


def render_portfolio_status_line() -> None:
    """One-line snapshot status under the section picker."""
    if not portfolio_data_ready():
        return
    loaded_at = st.session_state.get("portfolio_details_time")
    if loaded_at:
        st.caption(
            f"Portfolio snapshot {loaded_at.strftime('%d %b %H:%M')} — "
            "use **Reload live data** after ingest; prices auto-refresh every 5 minutes in the backend"
        )
