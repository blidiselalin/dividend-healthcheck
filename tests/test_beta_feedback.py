"""Tests for beta feedback storage."""

from __future__ import annotations

from pathlib import Path

from services.beta_feedback import BetaFeedbackStore


def test_submit_feedback(tmp_path: Path) -> None:
    store = BetaFeedbackStore(db_path=tmp_path / "users.db")
    record = store.submit(
        rating=5,
        message="Great yield chart",
        page="Command Center",
        email="test@example.com",
        user_id="user-1",
    )
    assert record.rating == 5
    assert record.message == "Great yield chart"
    assert record.page == "Command Center"
    assert record.email == "test@example.com"
