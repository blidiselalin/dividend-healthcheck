"""Research shortlist. Reads the market library and an optional language model."""

from __future__ import annotations

import streamlit as st

from services.research_screen import (
    resolve_llm_target,
    run_screen,
    screen_prompt,
    select_screen_candidates,
)
from services.shared_market_db import list_dividend_payers
from ui.session_keys import RESEARCH_SCREEN_RESULT_KEY


def render_research_screen() -> None:
    """Dividend-growth compounder shortlist. Does not change the portfolio."""
    st.markdown("##### Dividend growth screen")
    st.caption(
        "Research shortlist, not a buy recommendation. "
        "The model ranks stocks already in the shared library and must leave a metric "
        "empty when the library does not have it. Nothing here is added to your holdings."
    )
    target = resolve_llm_target()
    if target is None:
        st.info(
            "No language model is configured. Set DIVIDENDSCOPE_LOCAL_LLM_URL for a local "
            "OpenAI-compatible server, or DIVIDENDSCOPE_LLM_API_URL plus "
            "DIVIDENDSCOPE_LLM_API_KEY. A Hugging Face token also works."
        )
        return

    payers = list_dividend_payers()
    candidates = select_screen_candidates(payers, limit=600)
    st.caption(
        f"Model: {target.kind} · {target.model or 'default'}. "
        f"Eligible library names: {len(candidates)}."
    )
    with st.expander("Research prompt"):
        st.code(screen_prompt(), language="text")
    review_limit = int(
        st.number_input(
            "Stocks per run",
            min_value=1,
            max_value=40,
            value=10,
            step=1,
            key="research_screen_limit",
        )
    )
    available_count = len(candidates)
    candidates = candidates[:review_limit]
    st.metric("Eligible stocks available", available_count)
    st.caption(f"This run will review {len(candidates)} of the requested {review_limit} stocks.")
    if available_count < review_limit:
        st.warning(
            f"The eligible stock count is {available_count}, below the requested {review_limit}. "
            "The call limit cannot create missing market data."
        )
        if st.button("Load more stocks", key="research_screen_load_more"):
            from services.deferred_startup import schedule_ensure_top_dividend

            job_id = schedule_ensure_top_dividend(limit=min(100, max(20, review_limit * 2)))
            if job_id:
                st.success(
                    "Loading stock data in Background tasks. Refresh the count when complete."
                )
            else:
                st.info(
                    "A library load may already be running. Starting one requires admin access."
                )
        if st.button("Refresh candidate count", key="research_screen_refresh_count"):
            st.rerun()
    st.caption(
        f"One ticker per call, up to {review_limit} calls. Financial fields, totals and "
        "the unchanged 55-column CSV are assembled by the app."
    )
    if not candidates:
        st.warning(
            "The shared library has no common stocks above $2B with a dividend yield. "
            "Ingest the market library before running the screen."
        )
        return

    if st.button("Run screen", type="primary", key="research_screen_run"):
        with st.spinner("Reviewing one ticker at a time…"):
            progress = st.progress(0.0, text="Starting ticker reviews…")

            def update_progress(done: int, total: int, symbol: str) -> None:
                progress.progress(done / total, text=f"Reviewed {done}/{total} · {symbol}")

            try:
                rows, failures = run_screen(candidates, target=target, on_progress=update_progress)
            except Exception:
                st.error("The screen could not complete. The previous result is retained.")
                return
            finally:
                progress.empty()
        st.caption(
            f"Reviewed {len(candidates) - len(failures)} stocks; "
            f"{len(rows)} reviews returned; {len(failures)} failed or not reviewed."
        )
        if failures:
            st.warning("; ".join(f"{symbol}: {reason}" for symbol, reason in failures.items()))
        if len(failures) == len(candidates):
            st.error("No reviews completed. The previous result is retained.")
            return
        st.session_state[RESEARCH_SCREEN_RESULT_KEY] = rows
        if not rows:
            st.info(
                f"No stocks qualified from {len(candidates)} eligible library candidates. "
                "Populate or refresh the shared market library to screen more companies. "
                "The prompt does not force a recommendation."
            )

    rows = st.session_state.get(RESEARCH_SCREEN_RESULT_KEY)
    if not rows:
        return
    import pandas as pd

    frame = pd.DataFrame(rows)
    show = [
        "rank",
        "ticker",
        "company_name",
        "sector",
        "dividend_yield_pct",
        "dividend_cagr_5y_pct",
        "valuation_view",
        "total_score",
        "decision_label",
        "portfolio_phase",
        "source_confidence",
    ]
    st.dataframe(frame[show], use_container_width=True, hide_index=True)
    st.download_button(
        "Download CSV",
        frame.to_csv(index=False),
        "dividend_growth_screen.csv",
        "text/csv",
        key="research_screen_csv",
    )
    with st.expander("Reasons and risks"):
        for row in rows:
            st.markdown(
                f"**{row['rank']}. {row['ticker']}** — {row['decision_label']}. "
                f"{row['decision_reason']}"
            )
            if row["key_risks"]:
                st.caption(row["key_risks"])
