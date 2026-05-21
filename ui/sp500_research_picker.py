"""
Pick any S&P 500 symbol from the portfolio home page for full analysis.
"""

from __future__ import annotations

from typing import List, Optional

import streamlit as st

from config import DELISTED_SYMBOLS


@st.cache_data(ttl=86400, show_spinner=False)
def sp500_symbol_list() -> List[str]:
    """Cached S&P 500 tickers (shared library universe)."""
    from data_ingestion.sp500_universe import get_sp500_symbols

    return sorted(
        symbol.upper()
        for symbol in get_sp500_symbols()
        if symbol.upper() not in DELISTED_SYMBOLS
    )


def filter_sp500_symbols(
    symbols: List[str],
    query: str,
    *,
    limit: Optional[int] = None,
) -> List[str]:
    """
    Match ticker substring (case-insensitive).

    When ``limit`` is None and the query is empty, returns the full S&P list.
    When searching, ``limit`` caps matches for UI responsiveness (default 200).
    """
    needle = query.strip().upper()
    if not needle:
        return symbols if limit is None else symbols[:limit]
    cap = limit if limit is not None else 200
    return [symbol for symbol in symbols if needle in symbol][:cap]


def render_sp500_research_picker(*, key_prefix: str = "home") -> None:
    """
    Search and analyze any S&P 500 name using the shared market database.

    Shown on the main portfolio page (empty or with holdings).
    """
    from ui.portfolio_home import set_sp500_research_selection

    symbols = sp500_symbol_list()
    st.markdown("### Research any S&P 500 stock")
    st.caption(
        f"Choose from **{len(symbols)}** S&P names in the shared library — "
        "full dividend analysis without adding to your portfolio."
    )

    search = st.text_input(
        "Search ticker",
        key=f"{key_prefix}_sp500_search",
        placeholder="Type symbol, e.g. VZ, KO, AAPL, MSFT",
    )
    filtered = filter_sp500_symbols(symbols, search)
    if search.strip() and not filtered:
        st.warning("No S&P tickers match that search.")
        return

    if not search.strip():
        st.caption(
            f"Dropdown lists all **{len(filtered)}** S&P tickers (scroll or type above to narrow)."
        )
    elif len(filtered) >= 200:
        st.caption(f"Showing first **{len(filtered)}** matches — type more characters to narrow.")

    default_symbol = filtered[0] if filtered else "KO"
    if default_symbol not in filtered:
        default_symbol = filtered[0]

    pick = st.selectbox(
        "S&P 500 ticker",
        options=filtered,
        index=filtered.index(default_symbol) if default_symbol in filtered else 0,
        key=f"{key_prefix}_sp500_pick",
        help="Full S&P 500 list when search is empty; type in the box above to filter.",
    )

    if st.button(
        "Analyze selected stock",
        type="primary",
        key=f"{key_prefix}_sp500_analyze",
        use_container_width=False,
    ):
        nav = filtered if search.strip() else None
        set_sp500_research_selection(pick, nav_symbols=nav)
