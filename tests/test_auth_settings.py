"""Tests for auth settings helpers."""
# ruff: noqa: S101

from __future__ import annotations

import pytest

from auth.settings import invite_only_signup, is_email_allowed


def test_invite_only_when_allowlist_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auth.settings.allowed_emails", lambda: frozenset({"a@example.com"}))
    assert invite_only_signup() is True
    assert is_email_allowed("a@example.com") is True
    assert is_email_allowed("other@example.com") is False


def test_open_signup_without_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auth.settings.allowed_emails", lambda: frozenset())
    assert invite_only_signup() is False
    assert is_email_allowed("new@example.com") is True
