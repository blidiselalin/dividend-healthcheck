"""Tests for demo test user and portfolio home examples."""

from __future__ import annotations

from pathlib import Path

import pytest

from auth.demo_portfolio import DEMO_HOLDINGS, ensure_demo_database, reset_demo_database
from auth.test_user import TEST_USER_ID, is_test_user, is_test_user_email
from auth.test_user import test_user_current as build_test_user
from ui.portfolio_home import HOME_EXAMPLES, apply_example_action


def test_test_user_identity():
    user = build_test_user()
    assert user.id == TEST_USER_ID
    assert is_test_user(user) is True
    assert is_test_user_email(user.email) is True


def test_demo_database_seed(tmp_path: Path):
    db = tmp_path / "portfolio.db"
    assert ensure_demo_database(db) is True
    assert ensure_demo_database(db) is False

    import sqlite3

    count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
    assert count == len(DEMO_HOLDINGS)


def test_reset_demo_database(tmp_path: Path):
    db = tmp_path / "portfolio.db"
    ensure_demo_database(db)
    reset_demo_database(db)
    assert not db.exists()


def test_home_examples_structure():
    assert len(HOME_EXAMPLES) == 3
    kinds = {item["kind"] for item in HOME_EXAMPLES}
    assert kinds == {"holding", "section"}


def test_apply_example_action_holding(monkeypatch):
    session: dict = {}

    class FakeSession:
        def __getitem__(self, key):
            return session[key]

        def __setitem__(self, key, value):
            session[key] = value

        def get(self, key, default=None):
            return session.get(key, default)

    monkeypatch.setattr("ui.portfolio_home.st.session_state", FakeSession())
    from ui.portfolio_home import PORTFOLIO_VIEW_HOLDING

    example = next(e for e in HOME_EXAMPLES if e["kind"] == "holding")
    apply_example_action(example)
    assert session["portfolio_selected_symbol"] == "KO"
    assert session["portfolio_view_mode"] == PORTFOLIO_VIEW_HOLDING
    assert session["portfolio_analysis_ready"] is True
