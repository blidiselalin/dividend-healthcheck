"""S&P 500 research picker helpers."""

from __future__ import annotations

from ui.sp500_research_picker import filter_sp500_symbols, sp500_symbol_list


def test_filter_sp500_symbols_substring() -> None:
    symbols = ["AAPL", "ABBV", "KO", "VZ", "MSFT"]
    assert filter_sp500_symbols(symbols, "V") == ["ABBV", "VZ"]
    assert filter_sp500_symbols(symbols, "AA") == ["AAPL"]


def test_filter_sp500_symbols_empty_query_returns_head() -> None:
    symbols = ["KO", "PEP", "JNJ"]
    assert filter_sp500_symbols(symbols, "", limit=2) == ["KO", "PEP"]


def test_sp500_symbol_list_loads() -> None:
    symbols = sp500_symbol_list()
    assert len(symbols) >= 400
    assert "AAPL" in symbols
    assert "KO" in symbols


def test_set_sp500_research_selection_keys() -> None:
    from ui.portfolio_home import set_sp500_research_selection

    class FakeState(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    state = FakeState()
    import ui.portfolio_home as home

    original = home.st

    class FakeSt:
        session_state = state

        @staticmethod
        def rerun():
            pass

    home.st = FakeSt()
    try:
        set_sp500_research_selection("msft", nav_symbols=["MSFT", "META"])
    finally:
        home.st = original

    assert state["portfolio_selected_symbol"] == "MSFT"
    assert state["portfolio_research_mode"] is True
    assert state["portfolio_nav_tickers"] == ["MSFT", "META"]
