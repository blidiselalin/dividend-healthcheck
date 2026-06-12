"""Tests for holdings summary UI helpers."""
# ruff: noqa: S101

from __future__ import annotations

from ui.portfolio_summary import _format_delta


def test_format_delta_with_percent() -> None:
    assert _format_delta(100.0, 1.25) == "+1.25%"


def test_format_delta_without_percent() -> None:
    assert _format_delta(100.0, None) is None


def test_format_delta_none_value() -> None:
    assert _format_delta(None, 1.0) is None
