"""
SQLite registry of signed-in Google accounts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from config import DATA_DIR

USERS_DB_PATH = DATA_DIR / "users.db"


@dataclass(frozen=True)
class AppUser:
    id: str
    email: str
    name: Optional[str]
    picture_url: Optional[str]
    created_at: datetime
    last_login_at: datetime
    is_active: bool
    is_admin: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class UserStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or USERS_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
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

    def get_by_email(self, email: str) -> Optional[AppUser]:
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
        name: Optional[str],
        picture_url: Optional[str],
        is_admin: bool = False,
    ) -> AppUser:
        from auth.migration import migrate_user_data_dir

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
                connection.execute(
                    """
                    UPDATE users
                    SET email = ?, name = ?, picture_url = ?, last_login_at = ?,
                        is_admin = MAX(is_admin, ?)
                    WHERE id = ?
                    """,
                    (email, name, picture_url, now, int(is_admin), user_id),
                )
            elif by_email:
                old_id = str(by_email["id"])
                if old_id != user_id:
                    migrate_user_data_dir(old_id, user_id)
                    connection.execute(
                        """
                        UPDATE users
                        SET id = ?, name = ?, picture_url = ?, last_login_at = ?,
                            is_admin = MAX(is_admin, ?)
                        WHERE lower(email) = ?
                        """,
                        (
                            user_id,
                            name,
                            picture_url,
                            now,
                            int(is_admin),
                            normalized_email,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE users
                        SET name = ?, picture_url = ?, last_login_at = ?,
                            is_admin = MAX(is_admin, ?)
                        WHERE id = ?
                        """,
                        (name, picture_url, now, int(is_admin), user_id),
                    )
            else:
                connection.execute(
                    """
                    INSERT INTO users (
                      id, email, name, picture_url, created_at, last_login_at,
                      is_active, is_admin
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (user_id, email, name, picture_url, now, now, int(is_admin)),
                )

        user = self.get_by_id(user_id)
        if user is None:
            raise RuntimeError("Failed to persist user after login")
        return user

    def get_by_id(self, user_id: str) -> Optional[AppUser]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def list_users(self) -> List[AppUser]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM users ORDER BY last_login_at DESC"
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def set_active(self, user_id: str, *, active: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (int(active), user_id),
            )
        return cursor.rowcount > 0

    def set_admin(self, user_id: str, *, admin: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (int(admin), user_id),
            )
        return cursor.rowcount > 0

    def count_users(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0]) if row else 0
