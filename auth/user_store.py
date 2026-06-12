"""
SQLite registry of signed-in Google accounts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DATA_DIR
from db.connection import migrate_portfolio_user_id, open_app_db, use_cloud_sql

USERS_DB_PATH = DATA_DIR / "users.db"


@dataclass(frozen=True)
class AppUser:
    id: str
    email: str
    name: str | None
    picture_url: str | None
    created_at: datetime
    last_login_at: datetime
    is_active: bool
    is_admin: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _admin_update_expr(*, is_postgres: bool) -> str:
    """Preserve admin if either existing row or login grants admin."""
    if is_postgres:
        # Works for BOOLEAN columns and legacy SMALLINT/INTEGER from SQLite import.
        return "(COALESCE(is_admin::int, 0) <> 0 OR ?::boolean)"
    return "MAX(is_admin, ?)"


def _bool_param(value: bool, *, is_postgres: bool) -> Any:
    return bool(value) if is_postgres else int(value)


class UserStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or USERS_DB_PATH)
        if not use_cloud_sql():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> Any:
        return open_app_db(self.db_path)

    def _ensure_schema(self) -> None:
        if use_cloud_sql():
            return
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY,
                  email TEXT NOT NULL UNIQUE,
                  name TEXT,
                  picture_url TEXT,
                  created_at TEXT NOT NULL,
                  last_login_at TEXT NOT NULL,
                  is_active INTEGER NOT NULL DEFAULT 1,
                  is_admin INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> AppUser:
        return AppUser(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            picture_url=row["picture_url"],
            created_at=_parse_dt(row["created_at"]),
            last_login_at=_parse_dt(row["last_login_at"]),
            is_active=bool(row["is_active"]),
            is_admin=bool(row["is_admin"]),
        )

    def get_by_email(self, email: str) -> AppUser | None:
        normalized = email.strip().lower()
        if not normalized:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(email) = ?", (normalized,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def upsert_from_login(
        self,
        *,
        user_id: str,
        email: str,
        name: str | None,
        picture_url: str | None,
        is_admin: bool = False,
    ) -> AppUser:
        now = _utc_now().isoformat()
        normalized_email = email.strip().lower()

        with self._connect() as connection:
            by_id = connection.execute(
                "SELECT id, email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            by_email = None
            if normalized_email:
                by_email = connection.execute(
                    "SELECT id, email FROM users WHERE lower(email) = ?",
                    (normalized_email,),
                ).fetchone()

            if by_id:
                admin_expr = _admin_update_expr(is_postgres=connection.is_postgres)
                query = f"""
                    UPDATE users
                    SET email = ?, name = ?, picture_url = ?, last_login_at = ?,
                        is_admin = {admin_expr}
                    WHERE id = ?
                    """  # noqa: S608
                connection.execute(
                    query,
                    (
                        email,
                        name,
                        picture_url,
                        now,
                        _bool_param(is_admin, is_postgres=connection.is_postgres),
                        user_id,
                    ),
                )
            elif by_email:
                old_id = str(by_email["id"])
                if old_id != user_id:
                    migrate_portfolio_user_id(old_id, user_id)
                    admin_expr = _admin_update_expr(is_postgres=connection.is_postgres)
                    query = f"""
                        UPDATE users
                        SET id = ?, name = ?, picture_url = ?, last_login_at = ?,
                            is_admin = {admin_expr}
                        WHERE lower(email) = ?
                        """  # noqa: S608
                    connection.execute(
                        query,
                        (
                            user_id,
                            name,
                            picture_url,
                            now,
                            _bool_param(is_admin, is_postgres=connection.is_postgres),
                            normalized_email,
                        ),
                    )
                else:
                    admin_expr = _admin_update_expr(is_postgres=connection.is_postgres)
                    query = f"""
                        UPDATE users
                        SET name = ?, picture_url = ?, last_login_at = ?,
                            is_admin = {admin_expr}
                        WHERE id = ?
                        """  # noqa: S608
                    connection.execute(
                        query,
                        (
                            name,
                            picture_url,
                            now,
                            _bool_param(is_admin, is_postgres=connection.is_postgres),
                            user_id,
                        ),
                    )
            else:
                if connection.is_postgres:
                    connection.execute(
                        """
                        INSERT INTO users (
                          id, email, name, picture_url, created_at, last_login_at,
                          is_active, is_admin
                        ) VALUES (?, ?, ?, ?, ?::timestamptz, ?::timestamptz, TRUE, ?)
                        """,
                        (user_id, email, name, picture_url, now, now, bool(is_admin)),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO users (
                          id, email, name, picture_url, created_at, last_login_at,
                          is_active, is_admin
                        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                        """,
                        (
                            user_id,
                            email,
                            name,
                            picture_url,
                            now,
                            now,
                            _bool_param(is_admin, is_postgres=False),
                        ),
                    )

        user = self.get_by_id(user_id)
        if user is None:
            raise RuntimeError("Failed to persist user after login")
        return user

    def get_by_id(self, user_id: str) -> AppUser | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_user(row) if row else None

    def list_users(self) -> list[AppUser]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM users ORDER BY last_login_at DESC").fetchall()
        return [self._row_to_user(row) for row in rows]

    def set_active(self, user_id: str, *, active: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (
                    _bool_param(active, is_postgres=connection.is_postgres),
                    user_id,
                ),
            )
            return bool(cursor.rowcount > 0)

    def set_admin(self, user_id: str, *, admin: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (
                    _bool_param(admin, is_postgres=connection.is_postgres),
                    user_id,
                ),
            )
            return bool(cursor.rowcount > 0)

    def count_users(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0]) if row else 0
