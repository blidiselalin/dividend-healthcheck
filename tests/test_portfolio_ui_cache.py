"""Portfolio UI cache staleness and session hydration."""
# ruff: noqa: S101

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_ui_cache import (
    _row_to_dict,
    cache_is_stale,
    ensure_portfolio_session_loaded,
    hydrate_session_from_disk,
)


def _detail_row(**overrides: Any) -> PortfolioDetailRow:
    base = {
        "company": "Coca-Cola",
        "ticker": "KO",
        "market_cap": 5_000_000_000,
        "pe_ratio": 15.0,
        "shares": 1.0,
        "current_price": 55.0,
        "current_value": 55.0,
        "avg_cost_per_share": 50.0,
        "acquisition_value": 50.0,
        "profit": 5.0,
        "profit_pct": 10.0,
        "estimated_avg_price": 50.0,
        "medium_price_365d": 52.0,
        "price_180d": 54.0,
        "price_365d": 50.0,
        "change_180d_pct": 2.0,
        "change_365d_pct": 10.0,
        "weight_pct": 5.0,
        "dividend_yield_pct": 3.0,
        "dividend_per_share": 1.5,
        "annual_income": 1.5,
        "dividend_weight_pct": 5.0,
        "income_weight_pct": 5.0,
        "dividends_paid": 0.0,
        "growth_years": 10,
        "commission": 0.0,
        "sector": "Consumer",
        "acquisition_share_pct": 5.0,
        "analyst_rating": "HOLD",
        "price_to_fcf": 10.0,
        "computed_dividend": "1.50 (3.00%)",
        "ex_dividend_date": None,
        "dividend_pay_date": None,
        "data_source": "test",
    }
    base.update(overrides)
    return PortfolioDetailRow(**base)


def _sample_bundle(*, saved_at: datetime | None = None) -> dict:
    saved = saved_at or datetime.now()
    return {
        "version": 1,
        "saved_at": saved.isoformat(),
        "rows": [_row_to_dict(_detail_row())],
        "portfolio_details_time": saved.isoformat(),
    }


def test_cache_is_stale_when_older_than_max_age() -> None:
    bundle = {
        "saved_at": (datetime.now() - timedelta(hours=48)).isoformat(),
        "rows": [{"symbol": "KO"}],
    }
    assert cache_is_stale(bundle) is True


def test_cache_is_stale_when_library_is_newer(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = datetime.now() - timedelta(days=6)
    bundle = {"saved_at": saved.isoformat(), "rows": [{"symbol": "KO"}]}
    monkeypatch.setattr(
        "services.portfolio_ui_cache.market_library_latest_update",
        lambda: datetime.now(),
    )
    assert cache_is_stale(bundle) is True


def test_cache_is_fresh_when_recent_and_library_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = datetime.now() - timedelta(hours=1)
    bundle = {"saved_at": saved.isoformat(), "rows": [{"symbol": "KO"}]}
    monkeypatch.setattr(
        "services.portfolio_ui_cache.market_library_latest_update",
        lambda: saved,
    )
    assert cache_is_stale(bundle) is False


def test_hydrate_uses_stale_cache_as_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "portfolio_ui_session.json"
    bundle = _sample_bundle(saved_at=datetime.now() - timedelta(days=10))
    cache_path.write_text(json.dumps(bundle), encoding="utf-8")

    class FakeSession(dict):
        def get(self, key: str, default: Any = None) -> Any:
            return super().get(key, default)

    session = FakeSession()

    monkeypatch.setattr("services.portfolio_ui_cache._cache_path", lambda: cache_path)
    monkeypatch.setattr(
        "services.portfolio_session.user_has_holdings_in_db",
        lambda: True,
    )
    monkeypatch.setattr("services.portfolio_session.is_demo_session", lambda: False)
    monkeypatch.setattr("streamlit.session_state", session, raising=False)
    monkeypatch.setattr(
        "services.portfolio_details_service.PortfolioDetailsService.enrich_rows_previous_close",
        lambda self, rows: rows,
    )

    with patch("services.portfolio_ui_cache.cache_is_stale", return_value=True):
        assert hydrate_session_from_disk() is True
    assert len(session.get("portfolio_details_rows") or []) == 1
    assert session.get("_portfolio_stale_cache_loaded") is True


def test_hydrate_sync_loads_from_db_when_no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession(dict):
        def get(self, key: str, default: Any = None) -> Any:
            return super().get(key, default)

    session = FakeSession()

    monkeypatch.setattr("services.portfolio_ui_cache._cache_path", lambda: Path("/nonexistent/cache.json"))
    monkeypatch.setattr(
        "services.portfolio_session.user_has_holdings_in_db",
        lambda: True,
    )
    monkeypatch.setattr("services.portfolio_session.is_demo_session", lambda: False)
    monkeypatch.setattr("streamlit.session_state", session, raising=False)
    monkeypatch.setattr(
        "services.portfolio_ui_cache.warm_portfolio_session_from_db",
        lambda **kwargs: session.update({"portfolio_details_rows": [_detail_row()]}) or True,
    )

    assert hydrate_session_from_disk() is True
    assert len(session.get("portfolio_details_rows") or []) == 1


def test_ensure_portfolio_session_loaded_delegates_to_hydrate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _hydrate() -> bool:
        calls.append("hydrate")
        return True

    monkeypatch.setattr("services.portfolio_ui_cache.hydrate_session_from_disk", _hydrate)

    assert ensure_portfolio_session_loaded() is True
    assert calls == ["hydrate"]


def test_hydrate_loads_fresh_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "portfolio_ui_session.json"
    bundle = _sample_bundle()
    cache_path.write_text(json.dumps(bundle), encoding="utf-8")

    class FakeSession(dict):
        pass

    session = FakeSession()

    monkeypatch.setattr("services.portfolio_ui_cache._cache_path", lambda: cache_path)
    monkeypatch.setattr(
        "services.portfolio_session.user_has_holdings_in_db",
        lambda: True,
    )
    monkeypatch.setattr("services.portfolio_session.is_demo_session", lambda: False)
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    with patch("services.portfolio_ui_cache.cache_is_stale", return_value=False):
        assert hydrate_session_from_disk() is True
    assert len(session.get("portfolio_details_rows") or []) == 1
