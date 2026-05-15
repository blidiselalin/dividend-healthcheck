"""
Dividend Kings Analyzer — Streamlit Application.

Analyze elite dividend stocks with 50+ consecutive years of dividend increases.
Built for income investors seeking reliable, growing dividend income.
"""

import os
import sys
from pathlib import Path

# Project root on path before any local imports
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

import streamlit as st


def _bootstrap_secrets_env() -> None:
    """Apply Streamlit Cloud secrets before config.py reads DATA_DIR."""
    try:
        for key in ("DIVIDENDSCOPE_CLOUD", "DIVIDENDSCOPE_DATA_DIR"):
            if key in st.secrets:
                os.environ.setdefault(key, str(st.secrets[key]))
    except Exception:
        pass


_bootstrap_secrets_env()

from ui.views import SingleStockView, FullAnalysisView, USE_ENHANCED_SERVICE, get_service_status
from ui.portfolio_details_view import PortfolioDetailsView
from ui.portfolio_risk_panel import render_portfolio_risk_monitor
from config import DATA_SOURCES


@st.cache_resource(
    show_spinner="Preparing database (portfolio sync, prices, delisted cleanup)…"
)
def _startup_db_maintenance() -> dict:
    """Run once per Streamlit server process (app restart)."""
    from config import is_cloud_runtime
    from services.db_price_refresh import refresh_vector_db_prices, remove_delisted_from_vector_db
    from services.portfolio_vector_sync import sync_portfolio_to_vector_db

    cloud = is_cloud_runtime()
    purge = remove_delisted_from_vector_db()
    portfolio_sync = sync_portfolio_to_vector_db(enrich_missing=not cloud)
    refresh = refresh_vector_db_prices() if not cloud else {"updated": 0, "skipped": 0}
    return {
        "purge": purge,
        "portfolio_sync": portfolio_sync,
        "refresh": refresh,
        "cloud_mode": cloud,
    }

# Page configuration
st.set_page_config(
    page_title="DividendScope",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _render_data_source_status() -> None:
    """Render data source status in sidebar."""
    st.sidebar.markdown("### 📊 Data Source")

    refresh_stats = st.session_state.get("db_price_refresh_stats")
    if refresh_stats:
        purge = refresh_stats.get("purge", {})
        portfolio_sync = refresh_stats.get("portfolio_sync", {})
        refresh = refresh_stats.get("refresh", refresh_stats)
        if purge.get("removed", 0) > 0:
            st.sidebar.caption(
                f"Removed {purge['removed']} delisted record(s) from DB"
            )
        if portfolio_sync.get("linked", 0) > 0:
            created = portfolio_sync.get("created", 0)
            st.sidebar.caption(
                f"Portfolio linked in vector DB ({portfolio_sync['linked']} holdings"
                + (f", {created} new" if created else "")
                + ")"
            )
        missing = portfolio_sync.get("still_missing") or []
        if missing:
            st.sidebar.warning(
                f"Vector DB missing: {', '.join(missing[:5])}"
                + ("…" if len(missing) > 5 else "")
            )
        if refresh.get("updated", 0) > 0:
            st.sidebar.caption(f"Latest prices saved to DB ({refresh['updated']} symbols)")
    
    if USE_ENHANCED_SERVICE:
        status = get_service_status()
        doc_count = status.get("document_count", 0)
        kings_count = status.get("dividend_kings", 0)
        is_db_primary = status.get("is_db_primary", False)
        
        if is_db_primary:
            st.sidebar.success(f"🗄️ **Vector DB** ({doc_count} stocks)")
            st.sidebar.caption(f"👑 {kings_count} Dividend Kings • Fast local data")
        else:
            st.sidebar.warning("🌐 **Public API** (DB empty)")
            st.sidebar.caption(
                "Run `python ingest_data.py --enrich` to populate"
            )
    else:
        st.sidebar.info("🌐 **Public API** only")
        st.sidebar.caption("Install chromadb for local caching")


def main() -> None:
    """Main application entry point."""
    maintenance = _startup_db_maintenance()
    st.session_state["db_price_refresh_stats"] = maintenance
    if maintenance.get("cloud_mode"):
        st.session_state.setdefault("portfolio_risk_cloud_deferred", True)

    # Header
    st.title("👑 DividendScope")
    st.markdown(
        "**Intelligent dividend analytics** — Analyze Dividend Kings, "
        "assess payout sustainability, and discover quality income investments"
    )
    
    # Sidebar navigation
    st.sidebar.header("Analysis Mode")
    analysis_options = ["Single Stock", "All Dividend Kings", "Portfolio Details"]
    default_analysis = st.session_state.get("analysis_type", analysis_options[0])
    if default_analysis not in analysis_options:
        default_analysis = analysis_options[0]

    analysis_type = st.sidebar.radio(
        "Choose analysis type",
        analysis_options,
        index=analysis_options.index(default_analysis),
        help=(
            "Single Stock: Deep dive into one company\n"
            "All Kings: Compare all qualified stocks\n"
            "Portfolio Details: Full holdings table from the local portfolio database"
        ),
    )
    st.session_state["analysis_type"] = analysis_type
    
    # Data source status
    _render_data_source_status()

    # Portfolio risk watchlist: full scan on load + hourly refresh (sidebar)
    render_portfolio_risk_monitor()
    
    # Render appropriate view
    if analysis_type == "Single Stock":
        SingleStockView.render()
    elif analysis_type == "Portfolio Details":
        PortfolioDetailsView.render()
    else:
        FullAnalysisView.render()
    
    # Footer with data source attribution
    st.sidebar.markdown("---")
    st.sidebar.markdown("### About")
    st.sidebar.markdown(
        """
        **Dividend Kings** are companies that have raised 
        their dividends for **50+ consecutive years**.
        
        This achievement requires:
        - Durable competitive advantages
        - Conservative financial management
        - Shareholder-focused leadership
        """
    )
    st.sidebar.caption(
        f"Data aggregated from {DATA_SOURCES['primary']}. "
        "For educational purposes only. Not financial advice."
    )


if __name__ == "__main__":
    main()
