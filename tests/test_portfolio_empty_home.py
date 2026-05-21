"""Empty portfolio home for real users vs test user."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.portfolio_session import is_demo_session, user_has_holdings_in_db


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
