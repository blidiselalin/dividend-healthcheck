"""Normalize date values from PostgreSQL (date/datetime) and SQLite (ISO text)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def parse_date(value) -> date:
    """Parse a DB column to ``date`` (never call ``date.fromisoformat`` on row values)."""
    if value is None:
        raise ValueError("date value is null")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("date value is empty")
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text:
        text = text.split(" ", 1)[0]
    return date.fromisoformat(text)


def parse_optional_date(value) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return parse_date(value)
