"""Unit tests for legacy file migration guards."""

from __future__ import annotations

from pathlib import Path


def test_migration_noops_under_postgres(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://local/test")

    from auth import migration

    user_dir = tmp_path / "users" / "u1"
    user_dir.mkdir(parents=True)
    assert migration.restore_owner_portfolio("u1", user_dir) is False
    assert migration.migrate_legacy_portfolio("u1", user_dir) is False
    assert migration.migrate_user_data_dir("old", "new") is False


def test_migration_copies_sqlite_files_without_postgres(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import sqlite3

    from auth import migration
    from config import DATA_DIR

    legacy = tmp_path / "data" / "portfolio.db"
    legacy.parent.mkdir(parents=True)
    with sqlite3.connect(legacy) as conn:
        conn.execute("CREATE TABLE holdings (symbol TEXT PRIMARY KEY, shares REAL NOT NULL)")
        conn.execute("INSERT INTO holdings VALUES ('KO', 1)")

    monkeypatch.setattr(migration, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(migration, "LEGACY_PORTFOLIO_DB", legacy)
    monkeypatch.setattr(migration, "LEGACY_SESSION_CACHE", tmp_path / "data" / "missing.pkl")
    monkeypatch.setattr(migration, "MIGRATION_MARKER", tmp_path / "data" / ".marker")

    user_dir = tmp_path / "data" / "users" / "owner"
    assert migration.restore_owner_portfolio("owner", user_dir) is True
    assert (user_dir / "portfolio.db").is_file()
