"""
Dividend Kings Analyzer — Streamlit Application.

Analyze elite dividend stocks with 50+ consecutive years of dividend increases.
Built for income investors seeking reliable, growing dividend income.
"""

import os
import sys
from pathlib import Path

# Some transitive dependencies still ship protos incompatible with newer
# protobuf C++ runtime builds; force Python implementation for compatibility.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import streamlit as st  # noqa: E402

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import DATA_SOURCES  # noqa: E402
from services.snapshot_sync_service import sync_snapshot_from_env  # noqa: E402
from ui.views import (  # noqa: E402
    USE_ENHANCED_SERVICE,
    FullAnalysisView,
    PortfolioView,
    SingleStockView,
    get_service_status,
)

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
            st.sidebar.caption("Run `python ingest_data.py --enrich` to populate")
    else:
        st.sidebar.info("🌐 **Public API** only")
        st.sidebar.caption("Install chromadb for local caching")


def main() -> None:
    """Main application entry point."""
    # Optional one-time snapshot import from remote URL (for Drive backup workflows).
    if "_snapshot_sync_done" not in st.session_state:
        try:
            sync_info = sync_snapshot_from_env()
            st.session_state["_snapshot_sync_done"] = True
            st.session_state["_snapshot_sync_info"] = sync_info
        except Exception:
            st.session_state["_snapshot_sync_done"] = True
            st.session_state["_snapshot_sync_info"] = {"enabled": True, "error": True}

    # Header
    st.title("👑 DividendScope")
    st.markdown(
        "**Intelligent dividend analytics** — Analyze Dividend Kings, "
        "assess payout sustainability, and discover quality income investments"
    )

    # Sidebar navigation
    st.sidebar.header("Analysis Mode")
    analysis_type = st.sidebar.radio(
        "Choose analysis type",
        ["Single Stock", "All Dividend Kings", "Interactive Brokers Portfolio"],
        help=(
            "Single Stock: Deep dive into one company\n"
            "All Kings: Compare all qualified stocks\n"
            "Interactive Brokers Portfolio: Analyze sheet-based portfolio positions"
        ),
    )

    # Data source status
    _render_data_source_status()

    sync_info = st.session_state.get("_snapshot_sync_info", {})
    if sync_info.get("enabled") and sync_info.get("imported"):
        st.sidebar.caption(f"☁️ Snapshot imported: {sync_info.get('imported')} docs")

    # Render appropriate view
    if analysis_type == "Single Stock":
        SingleStockView.render()
    elif analysis_type == "Interactive Brokers Portfolio":
        PortfolioView.render()
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
