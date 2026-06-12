"""Tests for access request store and allowlist integration."""
# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path

import pytest

from auth.access_requests import AccessRequestStatus, AccessRequestStore
from auth.settings import is_email_allowed


@pytest.fixture
def request_db(tmp_path: Path) -> AccessRequestStore:
    return AccessRequestStore(db_path=tmp_path / "users.db")


def test_submit_and_approve(request_db: AccessRequestStore) -> None:
    request_db.submit_request(
        email="New.User@Gmail.com",
        user_id="google-sub-1",
        name="New User",
        message="Please add me",
    )
    record = request_db.get_by_email("new.user@gmail.com")
    assert record is not None
    assert record.status == AccessRequestStatus.PENDING
    assert record.message == "Please add me"

    assert request_db.approve("new.user@gmail.com", reviewer_email="admin@example.com")
    approved = request_db.get_by_email("new.user@gmail.com")
    assert approved is not None
    assert approved.status == AccessRequestStatus.APPROVED
    assert approved.reviewed_by == "admin@example.com"


def test_reject_and_resubmit(request_db: AccessRequestStore) -> None:
    request_db.submit_request(email="x@example.com", user_id="sub-x")
    assert request_db.reject("x@example.com", reviewer_email="admin@example.com")

    rejected = request_db.get_by_email("x@example.com")
    assert rejected is not None
    assert rejected.status == AccessRequestStatus.REJECTED

    request_db.submit_request(email="x@example.com", user_id="sub-x", message="retry")
    again = request_db.get_by_email("x@example.com")
    assert again is not None
    assert again.status == AccessRequestStatus.PENDING


def test_is_email_allowed_includes_approved_grant(
    request_db: AccessRequestStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("auth.settings.allowed_emails", lambda: frozenset({"owner@example.com"}))
    monkeypatch.setattr(
        "auth.access_requests.AccessRequestStore",
        lambda db_path=None: AccessRequestStore(db_path=tmp_path / "users.db"),
    )

    assert is_email_allowed("stranger@example.com") is False
    request_db.submit_request(email="stranger@example.com", user_id="sub-2")
    request_db.approve("stranger@example.com", reviewer_email="owner@example.com")
    assert is_email_allowed("stranger@example.com") is True
