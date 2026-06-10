"""Empty portfolio home for real users vs test user."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.portfolio_session import is_demo_session, user_has_holdings_in_db
from ui.theme import (
    PORTFOLIO_NAV,
    PORTFOLIO_SECTION_LABELS,
    portfolio_section_key_from_label,
    resolve_portfolio_section_label,
)


def test_portfolio_nav_lists_all_sections_with_hints() -> None:
    assert len(PORTFOLIO_NAV) == 6
    assert PORTFOLIO_SECTION_LABELS == [
        "Home",
        "Holdings",
        "Dividend income",
        "Dividend growth",
        "Purchase journal",
        "Deposits & benchmarks",
    ]
    for label, _key, hint in PORTFOLIO_NAV:
        assert hint.strip()


def test_resolve_portfolio_section_label_defaults_and_normalizes() -> None:
    assert resolve_portfolio_section_label(None) == "Home"
    assert resolve_portfolio_section_label("") == "Home"
    assert resolve_portfolio_section_label("Unknown") == "Home"
    assert resolve_portfolio_section_label("Overview") == "Home"
    assert resolve_portfolio_section_label("Dividend income") == "Dividend income"


def test_portfolio_section_key_from_label() -> None:
    assert portfolio_section_key_from_label(None) == "dashboard"
    assert portfolio_section_key_from_label("Holdings") == "holdings"
    assert portfolio_section_key_from_label("Deposits & benchmarks") == "deposits"


def test_home_examples_include_ko_for_test_docs() -> None:
    from ui.portfolio_home import HOME_EXAMPLES

    symbols = [item.get("symbol") for item in HOME_EXAMPLES if item.get("kind") == "holding"]
    assert "KO" in symbols


def test_user_has_holdings_false_on_empty_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "portfolio.db"
    monkeypatch.setattr(
        "services.portfolio_session.resolve_current_portfolio_db",
        lambda: db,
    )
    assert user_has_holdings_in_db() is False


def test_is_demo_session_false_without_test_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auth.test_user.test_user_session_active", lambda: False)
    monkeypatch.setattr("auth.user_context.current_user", lambda: None)
    assert is_demo_session() is False
