"""Unit tests for portfolio UI cache hydration."""

from __future__ import annotations

import pickle
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from services.portfolio_details_service import PortfolioDetailRow
from services.portfolio_ui_cache import _row_to_dict, cache_is_stale, hydrate_session_from_disk


def _detail_row(**overrides) -> PortfolioDetailRow:
    base = dict(
        company="Coca-Cola",
        ticker="KO",
        market_cap=5_000_000_000,
        pe_ratio=15.0,
        shares=1.0,
        current_price=55.0,
        current_value=55.0,
        avg_cost_per_share=50.0,
        acquisition_value=50.0,
        profit=5.0,
        profit_pct=10.0,
        estimated_avg_price=50.0,
        medium_price_365d=52.0,
        price_180d=54.0,
        price_365d=50.0,
        change_180d_pct=2.0,
        change_365d_pct=10.0,
        weight_pct=5.0,
        dividend_yield_pct=3.0,
        dividend_per_share=1.5,
        annual_income=1.5,
        dividend_weight_pct=5.0,
        income_weight_pct=5.0,
        dividends_paid=0.0,
        growth_years=10,
        commission=0.0,
        sector="Consumer",
        acquisition_share_pct=5.0,
        analyst_rating="HOLD",
        price_to_fcf=10.0,
        computed_dividend="1.50 (3.00%)",
        ex_dividend_date=None,
        dividend_pay_date=None,
        data_source="test",
    )
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


def test_hydrate_skips_stale_cache(tmp_path: Path, monkeypatch):
    cache_path = tmp_path / "portfolio_ui_session.pkl"
    bundle = _sample_bundle(saved_at=datetime.now() - timedelta(days=10))
    cache_path.write_bytes(pickle.dumps(bundle))

    class FakeSession(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    session = FakeSession()

    monkeypatch.setattr("services.portfolio_ui_cache._cache_path", lambda: cache_path)
    monkeypatch.setattr(
        "services.portfolio_session.user_has_holdings_in_db",
        lambda: True,
    )
    monkeypatch.setattr("services.portfolio_session.is_demo_session", lambda: False)
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    with patch("services.portfolio_ui_cache.cache_is_stale", return_value=True):
        assert hydrate_session_from_disk() is False
    assert "portfolio_details_rows" not in session


def test_hydrate_loads_fresh_cache(tmp_path: Path, monkeypatch):
    cache_path = tmp_path / "portfolio_ui_session.pkl"
    bundle = _sample_bundle()
    cache_path.write_bytes(pickle.dumps(bundle))

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


def test_cache_is_stale_when_library_newer(monkeypatch):
    bundle = _sample_bundle(saved_at=datetime.now() - timedelta(days=3))
    monkeypatch.setattr(
        "services.portfolio_ui_cache.market_library_latest_update",
        lambda: datetime.now(),
    )
    assert cache_is_stale(bundle) is True
