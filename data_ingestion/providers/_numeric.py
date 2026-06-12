"""Shared numeric parsing for stock data providers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return None if result != result else result
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def as_percent(value: Any) -> float | None:
    """Normalize ratios: values in (0, 1) are treated as fractions."""
    result = as_float(value)
    if result is None:
        return None
    if 0 < abs(result) < 1:
        return result * 100
    return result


def parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_unix_date(value: Any) -> date | None:
    try:
        return datetime.fromtimestamp(value).date()
    except (ValueError, TypeError, OSError):
        return None
