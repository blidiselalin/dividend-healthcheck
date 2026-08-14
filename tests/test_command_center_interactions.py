"""AppTest coverage for public Product / Demo / Auth button behavior."""
# ruff: noqa: S101

from __future__ import annotations

from typing import Any

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


def _click(at: AppTest, label: str, *, timeout: float = 12) -> AppTest:
    matches = [b for b in at.button if b.label == label]
    assert matches, f"No button labelled {label!r}"
    matches[0].click().run(timeout=timeout)
    assert not at.exception, at.exception
    return at


def _feedback(at: AppTest) -> str:
    parts = [
        str(item.value) for group in (at.success, at.info, at.warning, at.error) for item in group
    ]
    return " ".join(parts)


def _button_keys(at: AppTest) -> list[str]:
    keys: list[str] = []
    for button in at.button:
        key = getattr(button, "key", None)
        if key:
            keys.append(str(key))
    return keys


def test_all_public_routes_render() -> None:
    for view, page in (
        ("product", "overview"),
        ("demo", "overview"),
        ("demo", "income"),
        ("demo", "risk"),
        ("demo", "research"),
        ("demo", "import"),
        ("auth", "overview"),
    ):
        at = _run_public(view=view, page=page)
        assert not at.exception
        route = resolve_public_route({"view": view, "page": page})
        if view == "product":
            assert route.view == PublicView.PRODUCT
        elif view == "auth":
            assert route.view == PublicView.AUTH
        else:
            assert route.view == PublicView.DEMO
            assert route.demo_page.value == page or page not in {p.value for p in DemoPage}


def test_active_buttons_are_disabled() -> None:
    product = _run_public()
    assert any(b.label == "Product" and b.disabled for b in product.button)
    demo = _run_public(view="demo", page="overview")
    assert any(b.label == "Overview" and b.disabled for b in demo.button)
    auth = _run_public(view="auth")
    assert any(b.label == "Create portfolio" and b.disabled for b in auth.button)


def test_hero_demo_and_auth_actions() -> None:
    at = _run_public()
    _click(at, "Try interactive demo")
    assert _qp(at, "view") == "demo"
    assert _qp(at, "page") == "overview"

    at = _run_public()
    hero_auth = [b for b in at.button if b.label == "Create portfolio" and not b.disabled]
    assert hero_auth
    hero_auth[-1].click().run()
    assert not at.exception
    assert _qp(at, "view") == "auth"


def test_authentication_return() -> None:
    at = _run_public(view="demo", page="income")
    _click(at, "Create portfolio")
    assert _qp(at, "view") == "auth"
    back = [b for b in at.button if "back" in b.label.lower()]
    assert back
    back[0].click().run()
    assert not at.exception
    assert _qp(at, "view") == "demo"
    assert _qp(at, "page") == "income"


def test_five_demo_navigation_buttons(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.stock_analysis_service.load_independent_stock_analysis",
        lambda *_a, **_k: None,
    )
    at = _run_public(view="demo", page="overview")
    for label, page in (
        ("Income", "income"),
        ("Risk", "risk"),
        ("Research", "research"),
        ("Sample import", "import"),
        ("Overview", "overview"),
    ):
        at = _click(at, label)
        assert _qp(at, "page") == page
        assert _qp(at, "view") == "demo"


def test_unchanged_holdings_feedback() -> None:
    at = _run_public(view="demo", page="overview")
    submit = [b for b in at.button if b.label == "Update sample holdings"]
    assert submit
    submit[0].click().run()
    assert not at.exception
    assert "No holding changes to apply." in _feedback(at)


def test_changed_holdings_show_income_delta() -> None:
    at = _run_public(view="demo", page="overview")
    before = estimate_annual_income_usd(default_guest_holdings())
    ko_inputs = [n for n in at.number_input if "KO" in (n.label or "")]
    assert ko_inputs
    ko_inputs[0].set_value(100.0)
    submit = [b for b in at.button if b.label == "Update sample holdings"]
    submit[0].click().run()
    assert not at.exception
    after = estimate_annual_income_usd(guest_holdings_from_session(_session_dict(at)))
    assert after > before
    text = _feedback(at)
    assert "Estimated annual income" in text
    assert f"${before:,.2f}" in text
    assert f"${after:,.2f}" in text


def test_valid_and_invalid_add() -> None:
    at = _run_public(view="demo", page="overview")
    _click(at, "Remove JNJ")
    assert "Removed JNJ" in _feedback(at)

    symbol_inputs = [t for t in at.text_input if t.label == "Ticker"]
    share_inputs = [n for n in at.number_input if n.label == "Shares"]
    assert symbol_inputs and share_inputs
    symbol_inputs[0].set_value("PG")
    share_inputs[0].set_value(12.0)
    _click(at, "Add holding")
    text = _feedback(at)
    assert "Added PG" in text
    assert "12" in text
    assert "Estimated annual income" in text
    symbols = {h.symbol for h in guest_holdings_from_session(_session_dict(at))}
    assert "PG" in symbols

    symbol_inputs = [t for t in at.text_input if t.label == "Ticker"]
    symbol_inputs[0].set_value("   ")
    _click(at, "Add holding")
    assert "Enter a ticker symbol." in _feedback(at)


def test_remove_and_final_holding_guard() -> None:
    at = _run_public(view="demo", page="overview")
    state = _session_dict(at)
    save_guest_holdings(
        state,
        [
            GuestHolding(
                symbol="KO",
                shares=25.0,
                avg_cost_per_share=58.0,
                company_name="Coca-Cola",
            ),
            GuestHolding(
                symbol="JNJ",
                shares=10.0,
                avg_cost_per_share=155.0,
                company_name="Johnson & Johnson",
            ),
        ],
    )
    at.session_state[GUEST_SESSION_KEY] = state[GUEST_SESSION_KEY]
    at.run()
    assert not at.exception
    _click(at, "Remove JNJ")
    symbols = {h.symbol for h in guest_holdings_from_session(_session_dict(at))}
    assert symbols == {"KO"}
    _click(at, "Remove KO")
    assert "at least one sample holding" in _feedback(at).lower()
    remaining = {h.symbol for h in guest_holdings_from_session(_session_dict(at))}
    assert remaining == {"KO"}


def test_reset_restores_defaults() -> None:
    at = _run_public(view="demo", page="overview")
    state = _session_dict(at)
    save_guest_holdings(
        state,
        [GuestHolding(symbol="PG", shares=10.0, avg_cost_per_share=160.0, company_name="P&G")],
    )
    at.session_state[GUEST_SESSION_KEY] = state[GUEST_SESSION_KEY]
    at.run()
    assert not at.exception
    _click(at, "Reset sample list")
    symbols = {h.symbol for h in guest_holdings_from_session(_session_dict(at))}
    assert symbols == {h.symbol for h in default_guest_holdings()}
    assert "Restored the diversified sample list" in _feedback(at)


def test_journey_overview_income_risk_auth() -> None:
    at = _run_public(view="demo", page="overview")
    _click(at, "Continue to Income")
    assert _qp(at, "page") == "income"
    _click(at, "Continue to Risk")
    assert _qp(at, "page") == "risk"
    risk_create = [b for b in at.button if b.label == "Create portfolio" and not b.disabled]
    assert risk_create
    risk_create[-1].click().run()
    assert not at.exception
    assert _qp(at, "view") == "auth"
    markdown = " ".join(str(m.value) for m in at.markdown)
    assert "AUTH_CONTROLS_VISIBLE" in markdown


def test_sample_import_load_and_apply() -> None:
    at = _run_public(view="demo", page="import")
    _click(at, "Load sample IBKR statement")
    preview = _session_dict(at).get("cc_demo_import_preview")
    assert isinstance(preview, dict)
    assert preview.get("open_positions") == 3
    assert "Sample statement loaded" in _feedback(at)
    _click(at, "Use this imported sample")
    assert _qp(at, "page") == "overview"
    by_symbol = {h.symbol: h for h in guest_holdings_from_session(_session_dict(at))}
    assert by_symbol["KO"].shares == 40.0
    assert by_symbol["O"].shares == 50.0
    assert "Imported sample applied" in _feedback(at)


def test_button_keys_are_unique_and_stable() -> None:
    at = _run_public(view="demo", page="overview")
    keys = _button_keys(at)
    assert "cc_nav_product" in keys
    assert "cc_nav_demo" in keys
    assert "cc_nav_auth" in keys
    assert "cc_demo_nav_overview" in keys
    assert "cc_demo_nav_income" in keys
    assert "cc_demo_nav_risk" in keys
    assert "cc_demo_nav_research" in keys
    assert "cc_demo_nav_import" in keys
    assert "cc_overview_to_income" in keys
    assert "cc_demo_add_btn" in keys
    assert "cc_demo_reset" in keys
    duplicates = [key for key in keys if keys.count(key) > 1]
    assert duplicates == []
