"""AppTest interaction checks for the public Command Center MVP journey."""
# ruff: noqa: S101

from __future__ import annotations

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from services.guest_playground import (
    GUEST_SESSION_KEY,
    GuestHolding,
    default_guest_holdings,
    estimate_annual_income_usd,
    guest_holdings_from_session,
    save_guest_holdings,
)
from ui.command_center_home import DemoPage, PublicView, resolve_public_route


def _public_app() -> None:
    import streamlit as st

    from ui.command_center_home import render_command_center_page

    def auth_block() -> None:
        st.markdown("AUTH_CONTROLS_VISIBLE")
        st.button("Continue in dev mode", key="apptest_auth_dev")

    render_command_center_page(auth_block=auth_block)


def _qp(at: AppTest, key: str) -> str:
    raw = at.query_params.get(key)
    if isinstance(raw, list):
        return str(raw[0]) if raw else ""
    return str(raw or "")


def _session_dict(at: AppTest) -> dict[str, Any]:
    """Copy AppTest session_state into a plain dict for service helpers."""
    filtered = getattr(at.session_state, "filtered_state", None)
    if isinstance(filtered, dict):
        return dict(filtered)
    return {}


def _run_public(**query: str) -> AppTest:
    at = AppTest.from_function(_public_app)
    for key, value in query.items():
        at.query_params[key] = value
    at.run()
    assert not at.exception, at.exception
    return at


def test_invalid_query_params_normalize_safely() -> None:
    route = resolve_public_route({"view": "nope", "page": "hack"})
    assert route.view == PublicView.PRODUCT
    assert route.demo_page == DemoPage.OVERVIEW
    route = resolve_public_route({"view": "auth", "page": "income"})
    assert route.view == PublicView.AUTH
    assert route.demo_page == DemoPage.OVERVIEW


def test_hero_demo_cta_opens_demo() -> None:
    at = _run_public()
    demo_buttons = [b for b in at.button if "interactive demo" in b.label.lower()]
    assert demo_buttons
    demo_buttons[0].click().run()
    assert not at.exception
    assert _qp(at, "view") == "demo"
    assert _qp(at, "page") == "overview"


def test_active_navigation_disabled_on_demo() -> None:
    at = _run_public(view="demo", page="overview")
    active = [b for b in at.button if b.label == "Overview · active"]
    assert active
    assert active[0].disabled is True


def test_create_portfolio_renders_auth_controls() -> None:
    at = _run_public(view="demo", page="risk")
    create_buttons = [b for b in at.button if "create portfolio" in b.label.lower()]
    assert create_buttons
    create_buttons[0].click().run()
    assert not at.exception
    assert _qp(at, "view") == "auth"
    markdown = " ".join(str(m.value) for m in at.markdown)
    assert "AUTH_CONTROLS_VISIBLE" in markdown


def test_update_shares_changes_annual_income() -> None:
    at = _run_public(view="demo", page="overview")
    before = estimate_annual_income_usd(default_guest_holdings())
    ko_inputs = [n for n in at.number_input if "KO" in (n.label or "")]
    assert ko_inputs
    ko_inputs[0].set_value(100.0)
    submit = [b for b in at.button if "Update sample holdings" in b.label]
    assert submit
    submit[0].click().run()
    assert not at.exception
    state = _session_dict(at)
    assert state.get(GUEST_SESSION_KEY)
    after = estimate_annual_income_usd(guest_holdings_from_session(state))
    assert after > before
    success = " ".join(str(s.value) for s in at.success)
    assert "Estimated annual income" in success


def test_reset_restores_default_values() -> None:
    at = _run_public(view="demo", page="overview")
    state = _session_dict(at)
    save_guest_holdings(
        state,
        [GuestHolding(symbol="VZ", shares=10.0, avg_cost_per_share=40.0, company_name="Verizon")],
    )
    at.session_state[GUEST_SESSION_KEY] = state[GUEST_SESSION_KEY]
    at.run()
    assert not at.exception
    reset = [b for b in at.button if "Reset to KO" in b.label]
    assert reset
    reset[0].click().run()
    assert not at.exception
    symbols = {h.symbol for h in guest_holdings_from_session(_session_dict(at))}
    assert symbols == {"KO", "JNJ", "O"}


def test_sample_import_parser_totals_and_apply() -> None:
    at = _run_public(view="demo", page="import")
    load = [b for b in at.button if b.label == "Load sample IBKR statement"]
    assert load
    load[0].click().run()
    assert not at.exception
    preview = _session_dict(at).get("cc_demo_import_preview")
    assert isinstance(preview, dict)
    assert preview.get("open_positions") == 3
    assert preview.get("trades") == 3
    assert preview.get("dividends") == 3

    use = [b for b in at.button if b.label == "Use this imported sample"]
    assert use
    use[0].click().run()
    assert not at.exception
    assert _qp(at, "page") == "overview"
    by_symbol = {h.symbol: h for h in guest_holdings_from_session(_session_dict(at))}
    assert by_symbol["KO"].shares == 40.0
    assert by_symbol["O"].shares == 50.0


def test_snapshot_mode_without_market_db_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import guest_playground as gp

    def _offline(*_a, **_k) -> None:
        raise RuntimeError("offline")

    monkeypatch.setattr(gp, "_try_enrich_from_library", _offline)
    dash = gp.build_guest_dashboard(default_guest_holdings())
    assert dash.data_mode == "snapshot"
    assert dash.annual_income_usd > 0


def test_continue_to_income_then_risk() -> None:
    at = _run_public(view="demo", page="overview")
    continue_income = [b for b in at.button if b.label == "Continue to Income"]
    assert continue_income
    continue_income[0].click().run()
    assert not at.exception
    assert _qp(at, "view") == "demo"
    assert _qp(at, "page") == "income"
    continue_risk = [b for b in at.button if b.label == "Continue to Risk"]
    assert continue_risk
    continue_risk[0].click().run()
    assert not at.exception
    assert _qp(at, "page") == "risk"


def test_create_portfolio_preserves_guest_holdings() -> None:
    at = _run_public(view="demo", page="overview")
    ko_inputs = [n for n in at.number_input if "KO" in (n.label or "")]
    assert ko_inputs
    ko_inputs[0].set_value(100.0)
    submit = [b for b in at.button if "Update sample holdings" in b.label]
    submit[0].click().run()
    assert not at.exception

    create = [b for b in at.button if b.label.lower() == "create portfolio"]
    assert create
    create[0].click().run()
    assert not at.exception
    assert _qp(at, "view") == "auth"
    markdown = " ".join(str(m.value) for m in at.markdown)
    assert "AUTH_CONTROLS_VISIBLE" in markdown
    by_symbol = {h.symbol: h for h in guest_holdings_from_session(_session_dict(at))}
    assert by_symbol["KO"].shares == 100.0


def test_auth_back_restores_demo_page() -> None:
    at = _run_public(view="demo", page="risk")
    create = [b for b in at.button if b.label.lower() == "create portfolio"]
    assert create
    create[0].click().run()
    assert _qp(at, "view") == "auth"
    back = [b for b in at.button if "back" in b.label.lower()]
    assert back
    back[0].click().run()
    assert not at.exception
    assert _qp(at, "view") == "demo"
    assert _qp(at, "page") == "risk"


def test_product_page_does_not_render_auth() -> None:
    at = _run_public()
    markdown = " ".join(str(m.value) for m in at.markdown)
    assert "AUTH_CONTROLS_VISIBLE" not in markdown
    labels = [b.label for b in at.button]
    assert "Explore the interactive demo" in labels
    assert "Create your portfolio" not in labels
    assert "Try the interactive demo" not in labels
    product_active = [b for b in at.button if b.label == "Product · active"]
    assert product_active
    assert product_active[0].disabled is True


def test_overview_has_no_quick_add_ticker_buttons() -> None:
    at = _run_public(view="demo", page="overview")
    quick = [
        b
        for b in at.button
        if (getattr(b, "key", None) or "").startswith("cc_demo_quick_")
        or b.label in {"KO", "JNJ", "O", "SCHD", "VZ", "MSFT"}
    ]
    assert quick == []


def test_optional_research_and_import_pages_render() -> None:
    research = _run_public(view="demo", page="research")
    assert not research.exception
    assert any(b.label == "Research · active" for b in research.button)
    import_page = _run_public(view="demo", page="import")
    assert not import_page.exception
    assert any(b.label == "Load sample IBKR statement" for b in import_page.button)


def test_research_failure_shows_snapshot_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.stock_analysis_service.load_independent_stock_analysis",
        lambda *_a, **_k: None,
    )
    at = _run_public(view="demo", page="research")
    assert not at.exception
    warnings = " ".join(str(w.value) for w in at.warning)
    assert "unavailable" in warnings.lower()
    assert "snapshot" in warnings.lower()
    assert any("Research spotlight" in (s.label or "") for s in at.selectbox)
