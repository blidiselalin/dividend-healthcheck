"""Tests for holdings summary UI helpers."""

from __future__ import annotations

from ui.portfolio_summary import _format_delta


def test_format_delta_with_percent():
    assert _format_delta(100.0, 1.25) == "+1.25%"


def test_format_delta_without_percent():
    assert _format_delta(100.0, None) is None


def test_format_delta_none_value():
    assert _format_delta(None, 1.0) is None
