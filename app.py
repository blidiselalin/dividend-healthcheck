"""
Dividend Kings Analyzer — Streamlit Application.

Analyze elite dividend stocks with 50+ consecutive years of dividend increases.
Built for income investors seeking reliable, growing dividend income.
"""

import logging
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
    BenchmarkView,
    FullAnalysisView,
    PortfolioView,
    SingleStockView,
    get_service_status,
)

logger = logging.getLogger(__name__)

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
            st.sidebar.success(f"🗄️ **PostgreSQL** ({doc_count} stocks)")
            st.sidebar.caption(f"👑 {kings_count} Dividend Kings • Fast local data")
        else:
            st.sidebar.warning("🌐 **Public API** (PostgreSQL empty)")
            st.sidebar.caption("Run `python ingest_data.py --enrich` to populate")
    else:
        st.sidebar.info("🌐 **Public API** only")
        st.sidebar.caption("Configure PostgreSQL for local data caching")


def _render_chatbot() -> None:
    try:
        from services.chatbot_service import (
            ChatMessage,
            coerce_chat_prompt,
            generate_reply,
            initial_messages,
        )

        st.sidebar.markdown("---")
        st.sidebar.markdown("### 💬 Assistant")

        if "chat_messages" not in st.session_state:
            st.session_state["chat_messages"] = initial_messages()

        for msg in st.session_state["chat_messages"]:
            with st.sidebar.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.sidebar.chat_input("Ask DividendScope..."):
            text = coerce_chat_prompt(prompt)
            st.session_state["chat_messages"].append({"role": "user", "content": text})
            with st.sidebar.chat_message("user"):
                st.markdown(text)

            with st.sidebar.chat_message("assistant"), st.spinner("Thinking..."):
                state_msgs = st.session_state["chat_messages"]
                messages = [ChatMessage(m["role"], m["content"]) for m in state_msgs]
                response = generate_reply(text, messages)
                st.markdown(response)
                new_msg = {"role": "assistant", "content": response}
                st.session_state["chat_messages"].append(new_msg)
    except Exception as e:
        logger.debug(f"Chatbot failed to load: {e}")


def main() -> None:  # noqa: C901
    """Main application entry point."""

    # Handle Authentication
    try:
        from auth.login_view import render_login_page
        from auth.settings import auth_required
        from auth.user_context import ensure_user_session

        if auth_required():
            user = ensure_user_session()
            if not user:
                render_login_page()
                return
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Auth system not fully configured: {e}")

    # Handle Admin Console
    try:
        from auth.user_context import is_app_admin
        from ui.admin_page import (
            is_admin_console_active,
            render_admin_page_if_active,
            set_admin_console_active,
        )

        if is_admin_console_active() and is_app_admin():
            if st.sidebar.button("← Back to App", use_container_width=True):
                set_admin_console_active(False)
                st.rerun()
            render_admin_page_if_active()
            return
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Admin console not available: {e}")

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
    mode_options = [
        "Single Stock",
        "All Dividend Kings",
        "Interactive Brokers Portfolio",
        "Benchmark Comparison",
    ]
    analysis_type = st.sidebar.radio(
        "Choose analysis type",
        mode_options,
        help=(
            "Single Stock: Deep dive into one company\n"
            "All Kings: Compare all qualified stocks\n"
            "Interactive Brokers Portfolio: Analyze sheet-based portfolio positions\n"
            "Benchmark Comparison: Compare portfolio performance vs ETFs"
        ),
    )

    # Data source status
    _render_data_source_status()

    sync_info = st.session_state.get("_snapshot_sync_info", {})
    if sync_info.get("enabled") and sync_info.get("imported"):
        st.sidebar.caption(f"☁️ Snapshot imported: {sync_info.get('imported')} docs")

    # Admin button in sidebar
    try:
        from auth.user_context import is_app_admin
        from ui.admin_page import set_admin_console_active

        if is_app_admin():
            st.sidebar.markdown("---")
            if st.sidebar.button("⚙️ Admin Console", use_container_width=True):
                set_admin_console_active(True)
                st.rerun()
    except ImportError:
        pass
    except Exception:
        pass

    # Render Chatbot
    try:
        from services.chatbot_service import is_chatbot_enabled

        if is_chatbot_enabled():
            _render_chatbot()
    except Exception:
        pass

    # Render appropriate view
    if analysis_type == "Single Stock":
        SingleStockView.render()
    elif analysis_type == "Interactive Brokers Portfolio":
        PortfolioView.render()
    elif analysis_type == "Benchmark Comparison":
        BenchmarkView.render()
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
