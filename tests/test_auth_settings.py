"""Tests for auth settings helpers."""
# ruff: noqa: S101

from __future__ import annotations

import pytest

from auth.settings import invite_only_signup, is_email_allowed


def test_invite_only_when_allowlist_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auth.settings._auth_section", lambda: {})
    monkeypatch.delenv("DIVIDENDSCOPE_INVITE_ONLY", raising=False)
    monkeypatch.setattr("auth.settings.auth_configured", lambda: True)
    monkeypatch.setattr("auth.settings.auth_disabled", lambda: False)
    monkeypatch.setattr("auth.settings.allowed_emails", lambda: frozenset({"a@example.com"}))
    assert invite_only_signup() is True
    assert is_email_allowed("a@example.com") is True
    assert is_email_allowed("other@example.com") is False


def test_invite_only_default_when_auth_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auth.settings._auth_section", lambda: {})
    monkeypatch.delenv("DIVIDENDSCOPE_INVITE_ONLY", raising=False)
    monkeypatch.setattr("auth.settings.auth_configured", lambda: True)
    monkeypatch.setattr("auth.settings.auth_disabled", lambda: False)
    monkeypatch.setattr("auth.settings.allowed_emails", lambda: frozenset())
    assert invite_only_signup() is True
    assert is_email_allowed("new@example.com") is False


def test_invite_only_override_false_allows_open_signup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auth.settings._auth_section", lambda: {"invite_only": False})
    monkeypatch.setattr("auth.settings.allowed_emails", lambda: frozenset())
    monkeypatch.setattr(
        "auth.access_requests.AccessRequestStore.is_approved",
        lambda self, email: False,
    )
    assert invite_only_signup() is False
    assert is_email_allowed("new@example.com") is True


def test_env_can_force_invite_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auth.settings._auth_section", lambda: {})
    monkeypatch.setenv("DIVIDENDSCOPE_INVITE_ONLY", "true")
    monkeypatch.setattr("auth.settings.auth_configured", lambda: False)
    monkeypatch.setattr("auth.settings.allowed_emails", lambda: frozenset())
    assert invite_only_signup() is True
