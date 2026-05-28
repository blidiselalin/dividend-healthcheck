"""Tests for user registry and auth settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from auth.settings import is_email_allowed
from auth.models import sanitize_user_id
from auth.user_store import UserStore, _admin_update_expr


def test_postgres_admin_update_expr():
    assert "GREATEST" not in _admin_update_expr(is_postgres=True)
    assert "is_admin::int" in _admin_update_expr(is_postgres=True)


def test_sanitize_user_id():
    assert sanitize_user_id("google-oauth2|12345")
    assert "/" not in sanitize_user_id("a/b/c")


def test_is_email_allowed_open_by_default(monkeypatch):
    monkeypatch.setattr("auth.settings.allowed_emails", lambda: frozenset())
    assert is_email_allowed("anyone@example.com") is True


def test_user_store_upsert(tmp_path: Path):
    db = tmp_path / "users.db"
    store = UserStore(db_path=db)
    user = store.upsert_from_login(
        user_id="uid1",
        email="test@example.com",
        name="Test User",
        picture_url=None,
        is_admin=True,
    )
    assert user.email == "test@example.com"
    assert user.is_admin is True

    again = store.upsert_from_login(
        user_id="uid1",
        email="test@example.com",
        name="Test User",
        picture_url=None,
        is_admin=False,
    )
    assert again.is_admin is True

    listed = store.list_users()
    assert len(listed) == 1

    store.set_active("uid1", active=False)
    assert store.get_by_id("uid1").is_active is False


def test_user_store_upsert_same_email_new_id(tmp_path: Path):
    """Dev login id then Google id for the same email should not raise."""
    store = UserStore(db_path=tmp_path / "users.db")
    store.upsert_from_login(
        user_id="dev_user_id",
        email="same@example.com",
        name="Dev",
        picture_url=None,
    )
    user = store.upsert_from_login(
        user_id="google_sub_123",
        email="same@example.com",
        name="Google User",
        picture_url="https://example.com/pic.png",
        is_admin=True,
    )
    assert user.id == "google_sub_123"
    assert user.email == "same@example.com"
    assert store.count_users() == 1


def test_restore_owner_portfolio_when_user_db_empty(tmp_path: Path, monkeypatch):
    from auth import migration

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    legacy_db = data_dir / "portfolio.db"
    user_dir = data_dir / "users" / "owner_id"

    import sqlite3

    with sqlite3.connect(legacy_db) as connection:
        connection.execute(
            "CREATE TABLE holdings (symbol TEXT PRIMARY KEY, shares REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO holdings (symbol, shares) VALUES ('KO', 10)"
        )

    user_dir.mkdir(parents=True)
    with sqlite3.connect(user_dir / "portfolio.db") as connection:
        connection.execute(
            "CREATE TABLE holdings (symbol TEXT PRIMARY KEY, shares REAL NOT NULL)"
        )

    monkeypatch.setattr(migration, "DATA_DIR", data_dir)
    monkeypatch.setattr(migration, "LEGACY_PORTFOLIO_DB", legacy_db)
    monkeypatch.setattr(migration, "LEGACY_SESSION_CACHE", data_dir / "missing.pkl")
    monkeypatch.setattr(migration, "MIGRATION_MARKER", data_dir / ".legacy_portfolio_migrated")

    assert migration.restore_owner_portfolio("owner_id", user_dir) is True
    assert migration._holding_count(user_dir / "portfolio.db") == 1


def test_user_store_set_admin(tmp_path: Path):
    store = UserStore(db_path=tmp_path / "users.db")
    store.upsert_from_login(
        user_id="u2",
        email="b@example.com",
        name=None,
        picture_url=None,
    )
    store.set_admin("u2", admin=True)
    assert store.get_by_id("u2").is_admin is True
