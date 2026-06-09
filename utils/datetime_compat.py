"""
Normalize datetimes for safe comparison and sorting.

Library code mixes naive local timestamps (``datetime.now()``) with
timezone-aware values from PostgreSQL (``timestamptz``). Always convert to
naive UTC before comparing or taking ``max``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Union

DateLike = Union[date, datetime]


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return a timezone-naive UTC datetime, or None."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def max_datetime(*values: Optional[datetime]) -> datetime:
    """Latest timestamp after normalizing mixed naive/aware inputs."""
    normalized = [to_naive_utc(value) for value in values if value is not None]
    if not normalized:
        return datetime.min
    return max(normalized)


def coerce_calendar_date(value: DateLike) -> date:
    """Normalize history keys to plain ``date`` objects."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.date()
    return value
