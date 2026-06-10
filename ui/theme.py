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
    ("Overview", "dashboard", "Performance, watchlists, and portfolio snapshot"),
    ("Holdings", "holdings", "Every position — filter, explore, compare with other holdings"),
    ("Income", "dividends", "Monthly calendar and cash received after tax"),
    ("Growth", "dividend_growth", "Dividend per share and year-over-year growth"),
    ("Journal", "journal", "Purchase lots and estimated share counts"),
    ("Deposits", "deposits", "Deposits, portfolio value, and index benchmarks"),
]

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
    st.sidebar.markdown(
        f'<p class="ds-sidebar-heading">{title}</p>',
        unsafe_allow_html=True,
    )


def main_content_start() -> None:
    """Top spacer so the first main-panel message is not under the app toolbar."""
    st.markdown('<div class="ds-main-top-spacer" aria-hidden="true"></div>', unsafe_allow_html=True)


def render_notice(message: str, *, kind: str = "info") -> None:
    """Full-width notice that wraps cleanly (no clipped alert text)."""
    css_class = {
        "info": "ds-notice ds-notice-info",
        "success": "ds-notice ds-notice-success",
        "warning": "ds-notice ds-notice-warning",
    }.get(kind, "ds-notice ds-notice-info")
    st.markdown(f'<div class="{css_class}">{message}</div>', unsafe_allow_html=True)


def inject_app_theme() -> None:
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
            background: #e0f2fe;
            border: 1px solid #7dd3fc;
            color: #0c4a6e;
        }
        .ds-notice-success {
            background: #dcfce7;
            border: 1px solid #86efac;
            color: #14532d;
        }
        .ds-notice-warning {
            background: #fef9c3;
            border: 1px solid #fde047;
            color: #713f12;
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
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.55rem 0.75rem 0.45rem;
            min-height: 5.5rem;
        }
        div[data-testid="stMetric"] label {
            font-size: 0.75rem;
            color: #64748b;
            line-height: 1.35 !important;
            min-height: 2.1em;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.25rem;
            font-weight: 600;
            color: #0f172a;
            line-height: 1.25 !important;
        }
        div[data-testid="stMetricDelta"] {
            overflow: visible !important;
            white-space: normal !important;
            line-height: 1.3 !important;
        }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] {
            gap: 0.65rem;
            align-items: stretch;
        }
        .ds-hero {
            background: linear-gradient(135deg, #0f766e 0%, #115e59 55%, #134e4a 100%);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 6px 20px rgba(15, 118, 110, 0.18);
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(*, title: str, subtitle: str, compact: bool = False) -> None:
    if compact:
        st.markdown(f"### {title}")
        st.caption(subtitle)
        return
    st.markdown(
        f'<div class="ds-hero"><h2>{title}</h2><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def pick_portfolio_section() -> str:
    """Section picker (full labels, no truncation). Returns internal section key."""
    default_label = st.session_state.get("portfolio_section_label", "Overview")
    if default_label not in PORTFOLIO_SECTION_LABELS:
        default_label = "Overview"

    label = st.selectbox(
        "View",
        PORTFOLIO_SECTION_LABELS,
        index=PORTFOLIO_SECTION_LABELS.index(default_label),
        key="portfolio_section_picker",
    )
    st.session_state["portfolio_section_label"] = label
    hint = PORTFOLIO_HINT_BY_LABEL.get(label, "")
    if hint:
        st.caption(hint)
    return PORTFOLIO_SECTION_BY_LABEL[label]


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
