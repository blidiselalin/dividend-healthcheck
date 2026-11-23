"""Tests for holdings summary UI helpers."""
# ruff: noqa: S101

from __future__ import annotations

from types import SimpleNamespace

from ui.portfolio_summary import _format_delta, build_portfolio_health


def test_format_delta_with_percent() -> None:
    assert _format_delta(100.0, 1.25) == "+1.25%"


def test_format_delta_without_percent() -> None:
    assert _format_delta(100.0, None) == "$+100.00"


def test_format_delta_none_value() -> None:
    assert _format_delta(None, 1.0) == "Reload live data for today's move"


def _row(**overrides: object) -> SimpleNamespace:
    base = {
        "ticker": "KO",
        "sector": "Staples",
        "current_value": 100.0,
        "weight_pct": 50.0,
        "income_weight_pct": 40.0,
        "price_stale": False,
        "market_cap": 1.0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_portfolio_health_uses_priced_weights_and_names_gaps() -> None:
    rows = [
        _row(
            ticker="KO",
            sector="Staples",
            current_value=75.0,
            weight_pct=75.0,
            income_weight_pct=80.0,
        ),
        _row(
            ticker="JNJ",
            sector="Health",
            current_value=25.0,
            weight_pct=25.0,
            income_weight_pct=20.0,
        ),
        _row(
            ticker="T",
            sector="Telecom",
            current_value=None,
            weight_pct=None,
            income_weight_pct=None,
            price_stale=True,
        ),
    ]

    health = build_portfolio_health(rows)

    assert health.sectors[0] == ("Staples", 75.0)
    assert health.largest_positions[0] == ("KO", 75.0)
    assert health.income_leaders[0] == ("KO", 80.0)
    assert health.unpriced == ("T",)
    assert health.stale_prices == ("T",)
