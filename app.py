"""
Dividend Kings Analyzer — Streamlit Application.
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from utils.logging_config import configure_app_logging, get_logger

configure_app_logging()
logger = get_logger("dividendscope.app")

import streamlit as st


def _bootstrap_secrets_env() -> None:
    try:
        for key in ("DIVIDENDSCOPE_CLOUD", "DIVIDENDSCOPE_DATA_DIR", "DATABASE_URL", "DIVIDENDSCOPE_DATABASE_URL"):
            if key in st.secrets:
                os.environ.setdefault(key, str(st.secrets[key]))
    except Exception:
        pass


_bootstrap_secrets_env()

try:
    from db.connection import ensure_schema, use_cloud_sql

    if use_cloud_sql():
        ensure_schema()
except Exception:
    pass

_PROCESS_BOOT_LOGGED = False


def _log_process_boot() -> None:
    global _PROCESS_BOOT_LOGGED
    if _PROCESS_BOOT_LOGGED:
        return
    _PROCESS_BOOT_LOGGED = True
    from config import DATA_DIR, is_cloud_runtime
    from auth.settings import auth_required

    logger.info(
        "DividendScope process started data_dir=%s cloud=%s auth_required=%s",
        DATA_DIR,
        is_cloud_runtime(),
        auth_required(),
    )


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
from services.portfolio_session import sync_portfolio_session_with_db
from services.portfolio_ui_cache import hydrate_session_from_disk, refresh_portfolio_after_library_update


@st.cache_resource(show_spinner=False)
def _startup_db_light() -> dict:
    from config import is_cloud_runtime
    from services.shared_market_db import shared_market_db_status

    market = shared_market_db_status()
    cov = market.get("sp500_coverage") or {}
    logger.info(
        "Shared market library storage=%s documents=%d sp500=%s/%s",
        market.get("storage"),
        market.get("document_count", 0),
        cov.get("analysed_sp500", "?"),
        cov.get("universe_total", "?"),
    )
    return {"cloud_mode": is_cloud_runtime(), "market_db": market}


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
        logger.debug("Auth: not signed in")
        render_login_page()
        return False

    registered = ensure_user_session()
    if registered is None:
        email = getattr(st.user, "email", "") or "unknown"
        logger.warning("Auth: access denied for %s", email)
        render_login_page(access_denied=True)
        return False

    return True


def _render_data_badge() -> None:
    """Compact analysed-stocks line (caption avoids large alert boxes clipping on scroll)."""
    from db.connection import use_cloud_sql

    status = get_service_status()
    doc_count = status.get("document_count", 0)
    if status.get("is_db_primary"):
        cov = status.get("sp500_coverage") or {}
        sp = (
            f" · S&P {cov.get('analysed_sp500', 0)}/{cov.get('universe_total', 0)}"
            if cov.get("universe_total")
            else ""
        )
        storage = "PostgreSQL" if use_cloud_sql() else "local library"
        st.sidebar.caption(f"Shared S&P library ({storage}): {doc_count} tickers{sp}")
        return

    if use_cloud_sql():
        st.sidebar.caption(
            "Shared S&P library empty — run: "
            "./scripts/update_cloud_docker.sh --ingest"
        )
        return

    if not USE_ENHANCED_SERVICE:
        st.sidebar.caption("Install chromadb for analysed stocks.")
        return

    st.sidebar.caption(
        "Shared S&P library empty — run: python ingest_data.py --ensure-sp500 --enrich-existing"
    )


def _render_sidebar_footer() -> None:
    st.sidebar.divider()
    with st.sidebar.expander("About DividendScope", expanded=False):
        render_about_body()
    _render_data_badge()
    st.sidebar.caption(
        f"Data: {DATA_SOURCES['primary']}. Educational use only — not financial advice."
    )


def main() -> None:
    _log_process_boot()
    inject_app_theme()

    if not _require_authentication():
        st.stop()

    sync_portfolio_session_with_db()
    from services.portfolio_dividend_sync_service import sync_received_dividends
    from services.portfolio_session import is_demo_session, user_has_holdings_in_db

    if not is_demo_session() and user_has_holdings_in_db():
        sync_received_dividends()
    if hydrate_session_from_disk():
        rows = st.session_state.get("portfolio_details_rows") or []
        logger.info("Portfolio session hydrated from disk (%d holdings)", len(rows))
    elif refresh_portfolio_after_library_update():
        rows = st.session_state.get("portfolio_details_rows") or []
        logger.info("Portfolio session auto-reloaded after library update (%d holdings)", len(rows))
    st.session_state["db_price_refresh_stats"] = _startup_db_light()

    st.session_state["analysis_type"] = NAV_PORTFOLIO
    render_portfolio_sidebar()
    render_account_sidebar()
    main_content_start()
    PortfolioDetailsView.render()
    _render_sidebar_footer()


if __name__ == "__main__":
    main()
