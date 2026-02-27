"""
Dividend Kings Analyzer — Streamlit Application.

Analyze elite dividend stocks with 50+ consecutive years of dividend increases.
Built for income investors seeking reliable, growing dividend income.
"""

import sys
from pathlib import Path

import streamlit as st

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ui.views import SingleStockView, FullAnalysisView, USE_ENHANCED_SERVICE, get_service_status
from config import DATA_SOURCES

# Page configuration
st.set_page_config(
    page_title="Dividend Kings Analyzer",
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
            st.sidebar.caption(
                "Run `python ingest_data.py --enrich` to populate"
            )
    else:
        st.sidebar.info("🌐 **Public API** only")
        st.sidebar.caption("Install chromadb for local caching")


def main() -> None:
    """Main application entry point."""
    # Header with true characteristic
    st.title("👑 Dividend Kings Analyzer")
    st.markdown(
        "**Elite dividend stocks with 50+ consecutive years of dividend increases** — "
        "Analyze the most reliable income investments in the market"
    )
    
    # Sidebar navigation
    st.sidebar.header("Analysis Mode")
    analysis_type = st.sidebar.radio(
        "Choose analysis type",
        ["Single Stock", "All Dividend Kings"],
        help="Single Stock: Deep dive into one company\nAll Kings: Compare all qualified stocks",
    )
    
    # Data source status
    _render_data_source_status()
    
    # Render appropriate view
    if analysis_type == "Single Stock":
        SingleStockView.render()
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
