"""Unit tests for Command Center public routing and demo tour."""
# ruff: noqa: S101

from __future__ import annotations

import pytest

from ui.command_center_demo import resolve_next_demo_step
from ui.command_center_home import DemoPage, PublicView, resolve_public_route


@pytest.mark.parametrize(
    ("params", "view", "page"),
    [
        ({}, PublicView.PRODUCT, DemoPage.OVERVIEW),
        ({"view": "product"}, PublicView.PRODUCT, DemoPage.OVERVIEW),
        ({"view": "product", "page": "overview"}, PublicView.PRODUCT, DemoPage.OVERVIEW),
        ({"view": "demo"}, PublicView.DEMO, DemoPage.OVERVIEW),
        ({"view": "demo", "page": "hack"}, PublicView.DEMO, DemoPage.OVERVIEW),
        ({"view": "demo", "page": "income"}, PublicView.DEMO, DemoPage.INCOME),
        ({"view": "demo", "page": "risk"}, PublicView.DEMO, DemoPage.RISK),
        ({"view": "nope", "page": "income"}, PublicView.PRODUCT, DemoPage.OVERVIEW),
        ({"view": ["demo"], "page": ["income"]}, PublicView.DEMO, DemoPage.INCOME),
    ],
)
def test_resolve_public_route(params, view, page) -> None:
    route = resolve_public_route(params)
    assert route.view == view
    assert route.demo_page == page


def test_resolve_next_demo_step_walkthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, object] = {}
    monkeypatch.setattr("ui.command_center_demo.st.session_state", state)

    step = resolve_next_demo_step()
    assert step.target_page == DemoPage.OVERVIEW

    state["cc_tour_adjusted"] = True
    assert resolve_next_demo_step().target_page == DemoPage.INCOME

    state["cc_tour_income_opened"] = True
    assert resolve_next_demo_step().target_page == DemoPage.RISK

    state["cc_tour_risk_opened"] = True
    assert resolve_next_demo_step().target_page == DemoPage.RESEARCH

    state["cc_tour_research_opened"] = True
    assert resolve_next_demo_step().target_page == DemoPage.IMPORT

    state["cc_tour_import_opened"] = True
    assert resolve_next_demo_step().target_page is None
