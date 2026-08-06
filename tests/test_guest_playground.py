"""Tests for pre-login guest playground."""
# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from services.guest_playground import (
    GUEST_MAX_HOLDINGS,
    GUEST_SESSION_KEY,
    GuestDashboard,
    GuestHolding,
    add_guest_holding,
    build_guest_dashboard,
    default_guest_holdings,
    guest_holdings_from_session,
    remove_guest_holding,
    save_guest_holdings,
    to_portfolio_holdings,
)


def test_default_guest_holdings_has_three_symbols() -> None:
    holdings = default_guest_holdings()
    assert len(holdings) == 3
    assert {h.symbol for h in holdings} == {"KO", "JNJ", "O"}


def test_add_guest_respects_max_holdings() -> None:
    session: dict = {}
    save_guest_holdings(
        session,
        [
            GuestHolding(symbol="A", shares=1.0, avg_cost_per_share=1.0),
            GuestHolding(symbol="B", shares=1.0, avg_cost_per_share=1.0),
            GuestHolding(symbol="C", shares=1.0, avg_cost_per_share=1.0),
        ],
    )
    _, err = add_guest_holding(session, symbol="D", shares=1.0)
    assert err is not None
    assert len(guest_holdings_from_session(session)) == GUEST_MAX_HOLDINGS


def test_add_guest_updates_existing_symbol() -> None:
    session: dict = {}
    original_cost = 58.0
    original_company = "Coca-Cola Co"
    save_guest_holdings(
        session,
        [
            GuestHolding(
                symbol="KO",
                shares=5.0,
                avg_cost_per_share=original_cost,
                company_name=original_company,
            )
        ],
    )
    add_guest_holding(session, symbol="KO", shares=25.0)
    holdings = guest_holdings_from_session(session)
    assert len(holdings) == 1
    assert holdings[0].shares == 25.0
    assert holdings[0].avg_cost_per_share == original_cost
    assert holdings[0].company_name == original_company


def test_add_guest_explicit_cost_update() -> None:
    session: dict = {}
    save_guest_holdings(
        session,
        [GuestHolding(symbol="KO", shares=5.0, avg_cost_per_share=50.0, company_name="Coca-Cola")],
    )
    add_guest_holding(session, symbol="KO", shares=5.0, avg_cost_per_share=61.0)
    holdings = guest_holdings_from_session(session)
    assert holdings[0].avg_cost_per_share == 61.0


def test_remove_guest_falls_back_to_defaults_when_empty() -> None:
    session: dict = {}
    for holding in default_guest_holdings():
        add_guest_holding(
            session,
            symbol=holding.symbol,
            shares=holding.shares,
            avg_cost_per_share=holding.avg_cost_per_share,
            company_name=holding.company_name,
        )
    for symbol in ("KO", "JNJ", "O"):
        remove_guest_holding(session, symbol)
    assert len(guest_holdings_from_session(session)) == 3
    assert {h.symbol for h in guest_holdings_from_session(session)} == {"KO", "JNJ", "O"}


def test_reset_restores_default_symbols() -> None:
    session: dict = {}
    save_guest_holdings(session, [GuestHolding(symbol="VZ", shares=10.0, avg_cost_per_share=1.0)])
    save_guest_holdings(session, default_guest_holdings())
    assert {h.symbol for h in guest_holdings_from_session(session)} == {"KO", "JNJ", "O"}


def test_navigation_does_not_clear_holdings() -> None:
    session: dict = {}
    save_guest_holdings(
        session,
        [GuestHolding(symbol="KO", shares=12.0, avg_cost_per_share=50.0)],
    )
    from ui.command_center_home import resolve_public_route

    _ = resolve_public_route({"view": "demo", "page": "income"})
    holdings = guest_holdings_from_session(session)
    assert holdings[0].shares == 12.0
    assert session.get(GUEST_SESSION_KEY)


def test_to_portfolio_holdings_builds_acquisition_value() -> None:
    guest = [
        GuestHolding(symbol="KO", shares=10.0, avg_cost_per_share=50.0, company_name="Coca-Cola")
    ]
    rows = to_portfolio_holdings(guest)
    assert len(rows) == 1
    assert rows[0].acquisition_value == 500.0


def test_portfolio_metrics_sum_and_yield() -> None:
    dashboard = GuestDashboard(
        holdings=[GuestHolding(symbol="KO", shares=10.0, avg_cost_per_share=50.0)],
        annual_income_usd=100.0,
        rows=[
            SimpleNamespace(current_value=1000.0, annual_income=60.0),
            SimpleNamespace(current_value=500.0, annual_income=40.0),
        ],
    )
    from services.guest_playground import _apply_portfolio_metrics

    _apply_portfolio_metrics(dashboard)
    assert dashboard.portfolio_value_usd == 1500.0
    assert dashboard.portfolio_yield_pct == round(100.0 / 1500.0 * 100, 2)


def test_portfolio_yield_none_when_zero_value() -> None:
    dashboard = GuestDashboard(annual_income_usd=100.0, rows=[])
    from services.guest_playground import _apply_portfolio_metrics

    _apply_portfolio_metrics(dashboard)
    assert dashboard.portfolio_value_usd == 0.0
    assert dashboard.portfolio_yield_pct is None


def test_build_guest_dashboard_empty_guest() -> None:
    dashboard = build_guest_dashboard([])
    assert dashboard.annual_income_usd == 0.0
    assert dashboard.portfolio_value_usd == 0.0
    assert dashboard.portfolio_yield_pct is None


def test_migrate_guest_holdings_to_empty_db(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "portfolio.db"
    session: dict = {}
    save_guest_holdings(
        session,
        [GuestHolding(symbol="KO", shares=12.0, avg_cost_per_share=40.0, company_name="Coca-Cola")],
    )
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    from data_ingestion.portfolio_store import PortfolioStore
    from services.guest_playground import migrate_guest_holdings_to_portfolio

    count = migrate_guest_holdings_to_portfolio(db)
    assert count == 1
    store = PortfolioStore(db_path=db, seed=False)
    assert [h.symbol for h in store.list_holdings()] == ["KO"]
