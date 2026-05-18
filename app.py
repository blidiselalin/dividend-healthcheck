"""
Dividend Kings Analyzer — Streamlit Application.
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

import streamlit as st


def _bootstrap_secrets_env() -> None:
    try:
        for key in ("DIVIDENDSCOPE_CLOUD", "DIVIDENDSCOPE_DATA_DIR"):
            if key in st.secrets:
                os.environ.setdefault(key, str(st.secrets[key]))
    except Exception:
        pass


_bootstrap_secrets_env()

from auth.login_view import render_login_page
from auth.settings import auth_required
from auth.test_user import test_user_session_active
from auth.user_context import ensure_user_session
from ui.auth_account_panel import render_account_sidebar
from ui.views import USE_ENHANCED_SERVICE, get_service_status
from ui.portfolio_details_view import PortfolioDetailsView
from ui.portfolio_sidebar import render_portfolio_sidebar
from ui.app_about import render_about_body
from ui.theme import (
    NAV_PORTFOLIO,
    inject_app_theme,
    main_content_start,
)
from config import DATA_SOURCES
from services.portfolio_ui_cache import hydrate_session_from_disk


@st.cache_resource(show_spinner=False)
def _startup_db_light() -> dict:
    from config import is_cloud_runtime

    return {"cloud_mode": is_cloud_runtime()}


st.set_page_config(
    page_title="DividendScope",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _require_authentication() -> bool:
    if test_user_session_active():
        ensure_user_session()
        return True

    if not auth_required():
        ensure_user_session()
        return True

    if not st.user.is_logged_in:
        render_login_page()
        return False

    registered = ensure_user_session()
    if registered is None:
        render_login_page(access_denied=True)
        return False

    return True


def _render_data_badge() -> None:
    """Compact analysed-stocks line (caption avoids large alert boxes clipping on scroll)."""
    if not USE_ENHANCED_SERVICE:
        st.sidebar.caption("Install chromadb for analysed stocks.")
        return

    status = get_service_status()
    doc_count = status.get("document_count", 0)
    if status.get("is_db_primary"):
        cov = status.get("sp500_coverage") or {}
        sp = (
            f" · S&P {cov.get('analysed_sp500', 0)}/{cov.get('universe_total', 0)}"
            if cov.get("universe_total")
            else ""
        )
        st.sidebar.caption(f"Analysed stocks: {doc_count}{sp}")
    else:
        st.sidebar.caption("Analysed stocks DB empty — run ingest locally.")


def _render_sidebar_footer() -> None:
    st.sidebar.divider()
    with st.sidebar.expander("About DividendScope", expanded=False):
        render_about_body()
    _render_data_badge()
    st.sidebar.caption(
        f"Data: {DATA_SOURCES['primary']}. Educational use only — not financial advice."
    )


def main() -> None:
    inject_app_theme()

    if not _require_authentication():
        st.stop()

    hydrate_session_from_disk()
    st.session_state["db_price_refresh_stats"] = _startup_db_light()

    st.session_state["analysis_type"] = NAV_PORTFOLIO
    render_portfolio_sidebar()
    render_account_sidebar()
    main_content_start()
    PortfolioDetailsView.render()
    _render_sidebar_footer()


if __name__ == "__main__":
    main()
