"""Integration-style tests for guidance analytics, terms, and routes."""

from __future__ import annotations

from services.dividend_terminology import DIVIDEND_TERMS, term_help
from services.guidance_analytics import (
    GUIDANCE_EVENTS_KEY,
    track_guidance_event,
)
from services.next_best_action import resolve_next_best_action
from services.portfolio_onboarding import build_guidance_context
from ui.portfolio_home import navigate_to_portfolio_section


def test_received_accrued_estimated_terms_are_separate() -> None:
    assert "received_dividend" in DIVIDEND_TERMS
    assert "accrued_dividend" in DIVIDEND_TERMS
    assert "estimated_dividend" in DIVIDEND_TERMS
    assert term_help("received_dividend") != term_help("estimated_dividend")
    assert "not yet paid" in term_help("accrued_dividend").lower()


def test_analytics_strips_sensitive_broker_fields() -> None:
    session: dict = {}
    track_guidance_event(
        "broker_import_completed",
        session=session,
        properties={
            "imported_records": 3,
            "account": "U1234567",
            "broker_account": "U1234567",
            "portfolio_value": 156399.08,
            "description": "Dividend CASH",
            "warning_count": 1,
        },
    )
    events = session[GUIDANCE_EVENTS_KEY]
    assert len(events) == 1
    props = events[0]["properties"]
    assert props["imported_records"] == 3
    assert props["warning_count"] == 1
    assert "account" not in props
    assert "broker_account" not in props
    assert "portfolio_value" not in props
    assert "description" not in props


def test_primary_action_routes_for_key_states() -> None:
    cases = [
        (
            build_guidance_context(
                has_portfolio=False,
                has_dividend_transactions=False,
                has_upcoming_dividends=False,
                session={},
            ),
            "manage:import",
        ),
        (
            build_guidance_context(
                has_portfolio=True,
                has_dividend_transactions=False,
                has_upcoming_dividends=False,
                session={},
                has_successful_import=False,
            ),
            "manage:import",
        ),
        (
            build_guidance_context(
                has_portfolio=True,
                has_dividend_transactions=True,
                has_upcoming_dividends=False,
                session={},
                has_successful_import=True,
            ),
            "dividends",
        ),
    ]
    for context, expected_route in cases:
        action = resolve_next_best_action(context)
        assert action.primary_action_route == expected_route


def test_primary_action_routes_map_to_known_sections() -> None:
    from ui.theme import PORTFOLIO_LABEL_BY_KEY

    assert PORTFOLIO_LABEL_BY_KEY["dividends"] == "Dividend income"
    assert PORTFOLIO_LABEL_BY_KEY["holdings"] == "Holdings"
    assert PORTFOLIO_LABEL_BY_KEY["dashboard"] == "Home"
    assert navigate_to_portfolio_section.__name__ == "navigate_to_portfolio_section"
