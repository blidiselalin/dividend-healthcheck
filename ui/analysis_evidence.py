"""
Show clear evidence of data sources and history intervals used in analysis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

from config import MAX_HISTORY_YEARS
from services.analysis_evidence import (
    Row,
    build_evidence_rows,
    build_portfolio_session_rows,
    fmt_date,
)

__all__ = [
    "Row",
    "build_evidence_rows",
    "build_portfolio_session_rows",
    "render_analysis_evidence",
    "render_portfolio_session_evidence",
    "render_analysis_evidence_footer",
]


def _render_evidence_table(rows: Sequence[Row], *, key_suffix: str) -> None:
    import pandas as pd
    import streamlit as st

    if not rows:
        return
    df = pd.DataFrame(list(rows), columns=["What", "Evidence"])
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "What": st.column_config.TextColumn(width="medium"),
            "Evidence": st.column_config.TextColumn(width="large"),
        },
        key=f"analysis_evidence_table_{key_suffix}",
    )


def render_analysis_evidence(
    symbol: str,
    *,
    data: Any = None,
    vector_doc: Any = None,
    yield_channel_data: Any = None,
    portfolio_prices_at: Optional[datetime] = None,
    expanded: bool = True,
) -> None:
    """Per-ticker panel: sources, intervals, and reload timestamps."""
    import streamlit as st

    rows = build_evidence_rows(
        symbol,
        data=data,
        vector_doc=vector_doc,
        yield_channel_data=yield_channel_data,
        portfolio_prices_at=portfolio_prices_at,
    )
    with st.expander("📋 Data & history behind this analysis", expanded=expanded):
        st.caption(
            "Every chart, score, and zone on this page is tied to the intervals and "
            "reload times below — verify before acting."
        )
        _render_evidence_table(rows, key_suffix=symbol.upper())


def render_portfolio_session_evidence(
    *,
    loaded_at: Optional[datetime] = None,
    holding_count: int = 0,
    charts_ready: int = 0,
    library_ready: int = 0,
    expanded: bool = False,
) -> None:
    """Portfolio-wide evidence (sidebar or holdings section)."""
    import streamlit as st

    if loaded_at is None:
        loaded_at = st.session_state.get("portfolio_details_time")
    if not holding_count:
        session_rows = st.session_state.get("portfolio_details_rows") or []
        holding_count = len(session_rows)
    if not charts_ready or not library_ready:
        preload = st.session_state.get("portfolio_yield_cache")
        docs = st.session_state.get("portfolio_vector_docs")
        if isinstance(preload, dict):
            charts_ready = charts_ready or len(preload)
        if isinstance(docs, dict):
            library_ready = library_ready or len(docs)

    rows = build_portfolio_session_rows(
        loaded_at=loaded_at,
        holding_count=holding_count,
        charts_ready=charts_ready,
        library_ready=library_ready,
    )
    with st.expander("📋 Portfolio data snapshot", expanded=expanded):
        st.caption(
            "Reload updates live prices and preloads yield-channel windows for your holdings."
        )
        _render_evidence_table(rows, key_suffix="portfolio_session")


def render_analysis_evidence_footer(
    symbol: str,
    *,
    data: Any = None,
    vector_doc: Any = None,
) -> None:
    """One-line footer under a holding report."""
    import streamlit as st

    doc_updated = getattr(vector_doc, "last_updated", None) if vector_doc else None
    stock_updated = getattr(data, "_last_updated", None) if data else None
    quality = getattr(data, "data_quality_score", None)
    parts = [f"**{symbol.upper()}**"]
    if doc_updated:
        parts.append(f"library {fmt_date(doc_updated)}")
    if stock_updated:
        parts.append(f"snapshot {fmt_date(stock_updated)}")
    if quality is not None:
        parts.append(f"quality {quality:.0f}%")
    parts.append(f"history ≤{MAX_HISTORY_YEARS}y")
    st.caption(" · ".join(parts))
