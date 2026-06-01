"""Unit tests for db.parsing helpers."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from db.parsing import parse_date, parse_optional_date


def test_parse_date_accepts_common_formats() -> None:
    assert parse_date("2024-06-15") == date(2024, 6, 15)
    assert parse_date("2024-06-15T12:00:00") == date(2024, 6, 15)
    assert parse_date(date(2024, 1, 2)) == date(2024, 1, 2)
    assert parse_date(datetime(2024, 6, 15, 14, 30)) == date(2024, 6, 15)


def test_parse_date_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_date("")
    with pytest.raises(ValueError, match="null"):
        parse_date(None)


def test_parse_optional_date() -> None:
    assert parse_optional_date(None) is None
    assert parse_optional_date("") is None
    assert parse_optional_date(date(2024, 3, 1)) == date(2024, 3, 1)
