"""Portfolio session sync (per-user DB vs UI cache)."""
# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from data_ingestion.portfolio_store import PortfolioStore
from services.portfolio_session import (
    sync_portfolio_session_with_db,
    user_has_holdings_in_db,
)


class _FakeSession(dict):
    def get(self, key: str, default: Any = None) -> Any:
        return super().get(key, default)

    def pop(self, key: str, default: Any = None) -> Any:
        return super().pop(key, default)


def test_user_has_holdings_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "portfolio.db"
    PortfolioStore(db_path=db, seed=False)
    monkeypatch.setattr(
        "services.portfolio_session.resolve_current_portfolio_db",
        lambda: db,
    )
    assert user_has_holdings_in_db() is False


def test_user_has_holdings_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "portfolio.db"
    store = PortfolioStore(db_path=db, seed=False)
    store.upsert_holding("KO", shares=1, avg_cost_per_share=50.0)
    monkeypatch.setattr(
        "services.portfolio_session.resolve_current_portfolio_db",
        lambda: db,
    )
    assert user_has_holdings_in_db() is True


def test_sync_clears_stale_session_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "portfolio.db"
    PortfolioStore(db_path=db, seed=False)
    monkeypatch.setattr(
        "services.portfolio_session.resolve_current_portfolio_db",
        lambda: db,
    )
    monkeypatch.setattr("services.portfolio_session.is_demo_session", lambda: False)

    session = _FakeSession(
        {
            "portfolio_details_rows": [{"ticker": "KO"}],
        }
    )
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    cleared: list[str] = []

    def _clear() -> None:
        cleared.append("session")

    def _clear_disk() -> None:
        cleared.append("disk")

    monkeypatch.setattr(
        "auth.user_context.clear_portfolio_session_state",
        _clear,
    )
    monkeypatch.setattr(
        "services.portfolio_ui_cache.clear_session_cache",
        _clear_disk,
    )
    monkeypatch.setattr(
        "services.portfolio_session.refresh_session_if_portfolio_db_changed",
        lambda **kwargs: False,
    )

    sync_portfolio_session_with_db()
    assert "session" in cleared
    assert "disk" in cleared
