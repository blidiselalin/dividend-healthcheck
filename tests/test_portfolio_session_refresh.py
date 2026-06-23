"""Tests for portfolio session refresh when DB fingerprint changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from data_ingestion.portfolio_store import PortfolioStore
from services.portfolio_session import refresh_session_if_portfolio_db_changed


class _FakeSession(dict):
    def get(self, key: str, default: Any = None) -> Any:
        return super().get(key, default)

    def pop(self, key: str, default: Any = None) -> Any:
        return super().pop(key, default)


def test_refresh_skips_when_symbols_match_and_no_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "portfolio.db"
    store = PortfolioStore(db_path=db, seed=False)
    store.upsert_holding("KO", shares=5.0, avg_cost_per_share=50.0)

    monkeypatch.setattr(
        "services.portfolio_session.resolve_current_portfolio_db",
        lambda: db,
    )
    monkeypatch.setattr("services.portfolio_session.is_demo_session", lambda: False)
    monkeypatch.setattr("services.portfolio_session.user_has_holdings_in_db", lambda: True)

    session = _FakeSession(
        {
            "portfolio_details_rows": [
                type("Row", (), {"ticker": "KO", "profit_pct": 1.0})(),
            ],
        }
    )
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    reloaded: list[bool] = []

    monkeypatch.setattr(
        "services.portfolio_refresh.reload_portfolio_session",
        lambda **kwargs: reloaded.append(True) or None,
    )

    assert refresh_session_if_portfolio_db_changed() is False
    assert not reloaded
    assert session.get("_portfolio_db_fingerprint")
