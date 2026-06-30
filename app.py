"""
Dividend Kings Analyzer — Streamlit Application.
"""
# ruff: noqa: E402

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from utils.yfinance_config import configure_yfinance

configure_yfinance()

from utils.logging_config import configure_app_logging, get_logger

configure_app_logging()
logger = get_logger("dividendscope.app")

import streamlit as st


def _bootstrap_secrets_env() -> None:
    try:
        for key in (
            "DIVIDENDSCOPE_CLOUD",
            "DIVIDENDSCOPE_DATA_DIR",
            "DATABASE_URL",
            "DIVIDENDSCOPE_DATABASE_URL",
            "HUGGINGFACE_API_KEY",
            "HF_TOKEN",
            "DIVIDENDSCOPE_CHATBOT_ENABLED",
            "DIVIDENDSCOPE_CHATBOT_MODEL",
        ):
            if key in st.secrets:
                os.environ.setdefault(key, str(st.secrets[key]))
    except Exception as exc:
        logger.debug("Streamlit secrets not available (expected outside cloud): %s", exc)


_bootstrap_secrets_env()

try:
    from db.connection import ensure_schema, use_cloud_sql

    if use_cloud_sql():
        ensure_schema()
except Exception as exc:
    logger.warning("Schema initialisation skipped: %s", exc)

_PROCESS_BOOT_LOGGED = False


def _log_process_boot() -> None:
    global _PROCESS_BOOT_LOGGED
    if _PROCESS_BOOT_LOGGED:
        return
    _PROCESS_BOOT_LOGGED = True
    from auth.settings import auth_required
    from config import DATA_DIR, is_cloud_runtime

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
from config import DATA_SOURCES
from services.deferred_startup import apply_background_results, schedule_startup_tasks
from services.portfolio_session import sync_portfolio_session_with_db
from ui.admin_page import render_admin_page_if_active, render_admin_sidebar_entry
from ui.app_about import render_about_body
from ui.auth_account_panel import render_account_sidebar
from ui.chatbot_widget import render_chatbot_widget
from ui.portfolio_details_view import PortfolioDetailsView
from ui.portfolio_sidebar import render_portfolio_sidebar
from ui.sidebar_progress_panel import render_sidebar_progress
from ui.theme import NAV_PORTFOLIO, inject_app_theme, main_content_start
from ui.views import USE_ENHANCED_SERVICE, get_service_status


@st.cache_resource(show_spinner=False)
def _startup_db_light() -> dict:
    from config import is_cloud_runtime
    from services.shared_market_db import shared_market_db_status

    market = shared_market_db_status(include_coverage=False)
    cov = market.get("sp500_coverage") or {}
    try:
        from data_ingestion.stock_enricher import log_provider_status

        log_provider_status(logger)
    except Exception as exc:
        logger.debug("Provider status log unavailable: %s", exc)
    try:
        from services.price_refresh_scheduler import start_price_refresh_scheduler

        if start_price_refresh_scheduler():
            logger.info("Background price refresh scheduler started (5-minute interval)")
    except Exception as exc:
        logger.warning("Price refresh scheduler not started: %s", exc)
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
    page_icon="💹",
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

    status = st.session_state.get("market_db_status")
    if not status:
        try:
            from services.shared_market_db import shared_market_db_status

            status = shared_market_db_status()
            st.session_state["market_db_status"] = status
        except Exception:
            status = get_service_status()

    doc_count = int(status.get("document_count") or 0)
    if doc_count > 0:
        cov = status.get("sp500_coverage") or {}
        if not cov and not status.get("_coverage_scheduled"):
            try:
                from services.deferred_startup import schedule_coverage_badge_refresh

                schedule_coverage_badge_refresh()
                status = dict(status)
                status["_coverage_scheduled"] = True
                st.session_state["market_db_status"] = status
            except Exception as exc:
                logger.debug("Coverage badge refresh could not be scheduled: %s", exc)
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
    from services.portfolio_session import is_demo_session, user_has_holdings_in_db

    apply_background_results()
    from services.portfolio_ui_cache import ensure_portfolio_session_loaded

    if ensure_portfolio_session_loaded():
        rows = st.session_state.get("portfolio_details_rows") or []
        logger.info("Portfolio session ready (%d holdings)", len(rows))

    schedule_startup_tasks(
        is_demo=is_demo_session(),
        has_holdings=user_has_holdings_in_db(),
    )
    boot = _startup_db_light()
    st.session_state["db_price_refresh_stats"] = boot
    st.session_state["market_db_status"] = boot.get("market_db") or {}

    st.session_state["analysis_type"] = NAV_PORTFOLIO
    render_sidebar_progress()
    render_portfolio_sidebar()
    render_account_sidebar()
    render_admin_sidebar_entry()
    render_chatbot_widget()
    main_content_start()
    if render_admin_page_if_active():
        _render_sidebar_footer()
        return
    PortfolioDetailsView.render()
    from ui.design_system import render_app_footer

    render_app_footer()
    _render_sidebar_footer()

    from services.portfolio_ui_cache import flush_session_cache_if_pending

    flush_session_cache_if_pending()


if __name__ == "__main__":
    main()
