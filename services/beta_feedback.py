"""
Beta user feedback — stored in the app database (same pattern as access_requests).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR
from db.connection import open_app_db, use_cloud_sql

FEEDBACK_DB_PATH = DATA_DIR / "users.db"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


@dataclass(frozen=True)
class BetaFeedbackRecord:
    id: int
    rating: int
    message: str
    page: str
    email: str | None
    user_id: str | None
    created_at: datetime


class BetaFeedbackStore:
    """SQLite / Postgres store for beta feedback."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or FEEDBACK_DB_PATH)
        if not use_cloud_sql():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        return open_app_db(self.db_path)

    def _ensure_schema(self) -> None:
        if use_cloud_sql():
            return
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS beta_feedback (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  rating INTEGER NOT NULL,
                  message TEXT NOT NULL,
                  page TEXT NOT NULL,
                  email TEXT,
                  user_id TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_beta_feedback_created
                ON beta_feedback (created_at)
                """
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> BetaFeedbackRecord:
        return BetaFeedbackRecord(
            id=int(row["id"]),
            rating=int(row["rating"]),
            message=str(row["message"] or ""),
            page=str(row["page"] or ""),
            email=row["email"],
            user_id=row["user_id"],
            created_at=_parse_dt(row["created_at"]),
        )

    def submit(
        self,
        *,
        rating: int,
        message: str,
        page: str,
        email: str | None = None,
        user_id: str | None = None,
    ) -> BetaFeedbackRecord:
        rating = max(1, min(5, int(rating)))
        text = (message or "").strip()
        if not text:
            raise ValueError("Message is required.")
        page_label = (page or "unknown").strip()[:200]
        now = _utc_now().isoformat()
        normalized_email = email.strip().lower() if email and email.strip() else None

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO beta_feedback (rating, message, page, email, user_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rating, text, page_label, normalized_email, user_id, now),
            )
            row_id = int(getattr(cursor, "lastrowid", 0) or 0)
            if row_id <= 0:
                row = connection.execute(
                    "SELECT id FROM beta_feedback ORDER BY id DESC LIMIT 1"
                ).fetchone()
                row_id = int(row["id"]) if row else 0

        return BetaFeedbackRecord(
            id=row_id,
            rating=rating,
            message=text,
            page=page_label,
            email=normalized_email,
            user_id=user_id,
            created_at=_utc_now(),
        )
