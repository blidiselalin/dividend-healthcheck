"""
Lightweight guidance analytics — session-scoped, no financial PII.

Events are appended to session state and mirrored to the app logger.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

GUIDANCE_EVENTS_KEY = "guidance_analytics_events"

ALLOWED_EVENTS = frozenset(
    {
        "getting_started_viewed",
        "getting_started_step_clicked",
        "getting_started_dismissed",
        "next_best_action_viewed",
        "next_best_action_clicked",
        "help_article_opened",
        "broker_import_started",
        "broker_import_completed",
        "broker_import_failed",
        "reconciliation_opened",
        "dividend_dashboard_opened",
        "upcoming_dividends_opened",
    }
)

# Properties that must never be logged (defense in depth).
_BLOCKED_PROPERTY_KEYS = frozenset(
    {
        "account",
        "account_id",
        "account_number",
        "broker_account",
        "credentials",
        "password",
        "token",
        "description",
        "transaction_description",
        "portfolio_value",
        "total_value",
        "amount",
        "cash",
        "net",
        "gross",
    }
)


def _sanitize_properties(properties: Mapping[str, Any] | None) -> dict[str, Any]:
    if not properties:
        return {}
    clean: dict[str, Any] = {}
    for key, value in properties.items():
        key_l = str(key).strip().lower()
        if key_l in _BLOCKED_PROPERTY_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            # Avoid logging long free-text that might include account numbers.
            if isinstance(value, str) and len(value) > 80:
                continue
            clean[str(key)] = value
    return clean


def track_guidance_event(
    event_name: str,
    *,
    session: dict[str, Any] | None = None,
    properties: Mapping[str, Any] | None = None,
) -> None:
    """Record a guidance event. No-ops for unknown event names."""
    name = (event_name or "").strip()
    if name not in ALLOWED_EVENTS:
        return

    payload = {
        "event": name,
        "at": datetime.now(UTC).isoformat(),
        "properties": _sanitize_properties(properties),
    }

    if session is not None:
        events = session.setdefault(GUIDANCE_EVENTS_KEY, [])
        if isinstance(events, list):
            events.append(payload)

    logger.info("guidance_event name=%s props=%s", name, payload["properties"])
