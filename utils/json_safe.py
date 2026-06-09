"""
JSON-safe values for PostgreSQL JSONB and stdlib ``json.dumps``.

Python's JSON encoder emits ``NaN`` / ``Infinity`` tokens that PostgreSQL rejects.
"""

from __future__ import annotations

import math
from typing import Any


def finite_float(value: Any, *, default: float | None = None) -> float | None:
    """Return a finite float or ``default`` when value is missing/NaN/Inf."""
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def sanitize_for_json(value: Any) -> Any:
    """Recursively replace NaN/Inf floats with ``None`` for valid JSON."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_json(item) for item in value]
    return value
