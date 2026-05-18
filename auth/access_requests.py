"""
Access requests from Google users who are not on the static invite list.
Admins approve in the sidebar; approved emails can sign in on next attempt.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from config import DATA_DIR

REQUESTS_DB_PATH = DATA_DIR / "users.db"


class AccessRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AccessRequest:
    email: str
    user_id: str
    name: Optional[str]
    picture_url: Optional[str]
    status: AccessRequestStatus
    requested_at: datetime
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[str]
    message: Optional[str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class AccessRequestStore:
    """SQLite store for access requests (same DB file as users)."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or REQUESTS_DB_PATH)
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
                CREATE TABLE IF NOT EXISTS access_requests (
                  email TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  name TEXT,
                  picture_url TEXT,
                  status TEXT NOT NULL DEFAULT 'pending',
                  message TEXT,
                  requested_at TEXT NOT NULL,
                  reviewed_at TEXT,
                  reviewed_by TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_access_requests_status
                ON access_requests (status)
                """
            )

    @staticmethod
    def _row_to_request(row: sqlite3.Row) -> AccessRequest:
        return AccessRequest(
            email=row["email"],
            user_id=row["user_id"],
            name=row["name"],
            picture_url=row["picture_url"],
            status=AccessRequestStatus(row["status"]),
            requested_at=_parse_dt(row["requested_at"]) or _utc_now(),
            reviewed_at=_parse_dt(row["reviewed_at"]),
            reviewed_by=row["reviewed_by"],
            message=row["message"],
        )

    def get_by_email(self, email: str) -> Optional[AccessRequest]:
        normalized = email.strip().lower()
        if not normalized:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM access_requests WHERE lower(email) = ?",
                (normalized,),
            ).fetchone()
        return self._row_to_request(row) if row else None

    def is_approved(self, email: str) -> bool:
        record = self.get_by_email(email)
        return record is not None and record.status == AccessRequestStatus.APPROVED

    def submit_request(
        self,
        *,
        email: str,
        user_id: str,
        name: Optional[str] = None,
        picture_url: Optional[str] = None,
        message: Optional[str] = None,
    ) -> AccessRequest:
        normalized = email.strip().lower()
        now = _utc_now().isoformat()
        existing = self.get_by_email(normalized)

        with self._connect() as connection:
            if existing and existing.status == AccessRequestStatus.APPROVED:
                return existing
            if existing and existing.status == AccessRequestStatus.PENDING:
                return existing
            if existing and existing.status == AccessRequestStatus.REJECTED:
                connection.execute(
                    """
                    UPDATE access_requests
                    SET user_id = ?, name = ?, picture_url = ?, status = 'pending',
                        message = ?, requested_at = ?, reviewed_at = NULL, reviewed_by = NULL
                    WHERE lower(email) = ?
                    """,
                    (user_id, name, picture_url, message, now, normalized),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO access_requests (
                      email, user_id, name, picture_url, status, message,
                      requested_at, reviewed_at, reviewed_by
                    ) VALUES (?, ?, ?, ?, 'pending', ?, ?, NULL, NULL)
                    """,
                    (normalized, user_id, name, picture_url, message, now),
                )

        result = self.get_by_email(normalized)
        if result is None:
            raise RuntimeError("Failed to save access request")
        return result

    def list_pending(self) -> List[AccessRequest]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM access_requests
                WHERE status = 'pending'
                ORDER BY requested_at ASC
                """
            ).fetchall()
        return [self._row_to_request(row) for row in rows]

    def count_pending(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM access_requests WHERE status = 'pending'"
            ).fetchone()
        return int(row[0]) if row else 0

    def approve(self, email: str, *, reviewer_email: str) -> bool:
        normalized = email.strip().lower()
        now = _utc_now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE access_requests
                SET status = 'approved', reviewed_at = ?, reviewed_by = ?
                WHERE lower(email) = ?
                """,
                (now, reviewer_email.strip().lower(), normalized),
            )
            return cursor.rowcount > 0

    def reject(self, email: str, *, reviewer_email: str) -> bool:
        normalized = email.strip().lower()
        now = _utc_now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE access_requests
                SET status = 'rejected', reviewed_at = ?, reviewed_by = ?
                WHERE lower(email) = ?
                """,
                (now, reviewer_email.strip().lower(), normalized),
            )
            return cursor.rowcount > 0
