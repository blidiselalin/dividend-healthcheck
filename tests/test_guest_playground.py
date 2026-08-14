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


def test_add_guest_rejects_blank_symbol() -> None:
    session: dict = {}
    holdings, err = add_guest_holding(session, symbol="  ", shares=1.0)
    assert err == "Enter a ticker symbol."
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


def test_remove_guest_rejects_last_holding() -> None:
    session: dict = {}
    save_guest_holdings(
        session,
        [GuestHolding(symbol="KO", shares=25.0, avg_cost_per_share=58.0, company_name="Coca-Cola")],
    )
    holdings, err = remove_guest_holding(session, "KO")
    assert err is not None
    assert "at least one" in err.lower()
    assert [h.symbol for h in holdings] == ["KO"]
    assert [h.symbol for h in guest_holdings_from_session(session)] == ["KO"]


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


def test_snapshot_received_sample_scales_with_annual_income(monkeypatch) -> None:
    from services import guest_playground as gp

    monkeypatch.setattr(gp, "_try_enrich_from_library", lambda *_a, **_k: None)
    dashboard = build_guest_dashboard(default_guest_holdings())
    expected_gross = round(dashboard.annual_income_usd * 0.25, 2)
    expected_tax = round(expected_gross * 0.15, 2)
    assert dashboard.sample_received_gross_usd == expected_gross
    assert dashboard.sample_withholding_usd == expected_tax
    assert dashboard.sample_received_net_usd == round(expected_gross - expected_tax, 2)


def test_unsupported_symbol_does_not_zero_snapshot_income(monkeypatch) -> None:
    from services import guest_playground as gp

    monkeypatch.setattr(gp, "_try_enrich_from_library", lambda *_a, **_k: None)
    session: dict = {}
    save_guest_holdings(
        session,
        [
            GuestHolding(symbol="KO", shares=25.0, avg_cost_per_share=58.0),
            GuestHolding(symbol="ZZZZ", shares=10.0, avg_cost_per_share=20.0),
        ],
    )
    dashboard = build_guest_dashboard(guest_holdings_from_session(session))
    assert dashboard.annual_income_usd > 0
    assert dashboard.data_mode == "snapshot"
    assert {h.symbol for h in dashboard.holdings} >= {"KO", "ZZZZ"}


def test_replace_empty_positions_restores_defaults() -> None:
    from services.guest_playground import replace_guest_holdings_from_positions

    session: dict = {}
    save_guest_holdings(session, [GuestHolding(symbol="VZ", shares=10.0, avg_cost_per_share=40.0)])
    holdings = replace_guest_holdings_from_positions(session, [])
    assert {h.symbol for h in holdings} == {"KO", "JNJ", "O"}


def test_snapshot_dashboard_without_market_db(monkeypatch) -> None:
    from services import guest_playground as gp

    def _boom(*_a, **_k):
        raise RuntimeError("library unavailable")

    monkeypatch.setattr(gp, "_try_enrich_from_library", _boom)
    holdings = default_guest_holdings()
    dashboard = build_guest_dashboard(holdings)
    assert dashboard.data_mode == "snapshot"
    assert dashboard.annual_income_usd > 0
    assert dashboard.near_term_income_usd > 0
    assert dashboard.safety_alerts
    assert dashboard.monthly_forecast
    assert dashboard.next_payouts
    assert "snapshot" in dashboard.provenance_label.lower()


def test_packaged_ibkr_sample_totals_from_parser() -> None:
    from services.guest_playground import load_packaged_ibkr_sample_preview

    preview = load_packaged_ibkr_sample_preview()
    assert preview.open_positions == 3
    assert preview.trades == 3
    assert preview.dividends == 3
    assert preview.withholdings == 2
    assert preview.deposits == 2
    assert {row[0] for row in preview.position_rows} == {"KO", "JNJ", "O"}


def test_use_imported_sample_replaces_guest_holdings() -> None:
    from services.guest_playground import apply_packaged_ibkr_sample_to_guest

    session: dict = {}
    save_guest_holdings(
        session,
        [GuestHolding(symbol="VZ", shares=10.0, avg_cost_per_share=40.0)],
    )
    holdings, preview = apply_packaged_ibkr_sample_to_guest(session)
    assert preview.open_positions == 3
    assert {h.symbol for h in holdings} == {"KO", "JNJ", "O"}
    by_symbol = {h.symbol: h for h in holdings}
    assert by_symbol["KO"].shares == 40.0
    assert by_symbol["JNJ"].shares == 8.0
    assert by_symbol["O"].shares == 50.0
    assert session.get("cc_demo_import_confirm")


def test_quantity_change_updates_snapshot_income(monkeypatch) -> None:
    from services import guest_playground as gp
    from services.guest_playground import estimate_annual_income_usd

    def _offline(*_a, **_k) -> None:
        raise RuntimeError("offline")

    monkeypatch.setattr(gp, "_try_enrich_from_library", _offline)
    session: dict = {}
    save_guest_holdings(session, default_guest_holdings())
    before = estimate_annual_income_usd(guest_holdings_from_session(session))
    add_guest_holding(session, symbol="KO", shares=100.0)
    after = estimate_annual_income_usd(guest_holdings_from_session(session))
    assert after > before
    dashboard = build_guest_dashboard(guest_holdings_from_session(session))
    assert dashboard.annual_income_usd == after
    assert dashboard.data_mode == "snapshot"


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


def test_migrate_guest_holdings_skips_nonempty_portfolio(tmp_path: Path, monkeypatch) -> None:
    from data_ingestion.portfolio_store import PortfolioStore
    from services.guest_playground import migrate_guest_holdings_to_portfolio

    db = tmp_path / "portfolio.db"
    store = PortfolioStore(db_path=db, seed=False)
    store.upsert_holding("MSFT", shares=1.0, avg_cost_per_share=100.0)

    session: dict = {}
    save_guest_holdings(
        session,
        [GuestHolding(symbol="KO", shares=12.0, avg_cost_per_share=40.0)],
    )
    monkeypatch.setattr("streamlit.session_state", session, raising=False)

    assert migrate_guest_holdings_to_portfolio(db) == 0
    assert [h.symbol for h in store.list_holdings()] == ["MSFT"]
    assert session.get(GUEST_SESSION_KEY) is None
