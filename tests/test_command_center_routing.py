"""Unit tests for Command Center public routing and demo tour."""
# ruff: noqa: S101

from __future__ import annotations

import pytest

from ui.command_center_demo import resolve_next_demo_step
from ui.command_center_home import (
    CC_RETURN_PAGE_KEY,
    CC_RETURN_VIEW_KEY,
    DemoPage,
    PublicView,
    navigate_public,
    navigate_to_auth,
    resolve_public_route,
    return_from_auth,
)


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
        ({"view": "demo", "page": "research"}, PublicView.DEMO, DemoPage.RESEARCH),
        ({"view": "demo", "page": "import"}, PublicView.DEMO, DemoPage.IMPORT),
        ({"view": "auth"}, PublicView.AUTH, DemoPage.OVERVIEW),
        ({"view": "auth", "page": "income"}, PublicView.AUTH, DemoPage.OVERVIEW),
        ({"view": "nope", "page": "income"}, PublicView.PRODUCT, DemoPage.OVERVIEW),
        ({"view": ["demo"], "page": ["income"]}, PublicView.DEMO, DemoPage.INCOME),
        ({"view": ["auth"]}, PublicView.AUTH, DemoPage.OVERVIEW),
    ],
)
def test_resolve_public_route(params, view, page) -> None:
    route = resolve_public_route(params)
    assert route.view == view
    assert route.demo_page == page


def test_navigate_to_auth_preserves_return_route(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, object] = {}
    query: dict[str, str] = {"view": "demo", "page": "risk"}

    class _Query(dict):
        def __setitem__(self, key: str, value: object) -> None:
            super().__setitem__(key, str(value))

    qp = _Query(query)
    monkeypatch.setattr("ui.command_center_home.st.session_state", state)
    monkeypatch.setattr("ui.command_center_home.st.query_params", qp)

    navigate_to_auth(source_section="hero")
    assert state[CC_RETURN_VIEW_KEY] == "demo"
    assert state[CC_RETURN_PAGE_KEY] == "risk"
    assert qp["view"] == "auth"
    assert qp["page"] == "overview"


def test_return_from_auth_restores_demo_page(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {
        CC_RETURN_VIEW_KEY: "demo",
        CC_RETURN_PAGE_KEY: "income",
    }

    class _Query(dict):
        def __setitem__(self, key: str, value: object) -> None:
            super().__setitem__(key, str(value))

    qp = _Query({"view": "auth", "page": "overview"})
    monkeypatch.setattr("ui.command_center_home.st.session_state", state)
    monkeypatch.setattr("ui.command_center_home.st.query_params", qp)

    return_from_auth()
    assert qp["view"] == "demo"
    assert qp["page"] == "income"


def test_return_from_auth_defaults_to_demo_overview(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Query(dict):
        def __setitem__(self, key: str, value: object) -> None:
            super().__setitem__(key, str(value))

    qp = _Query({"view": "auth", "page": "overview"})
    monkeypatch.setattr("ui.command_center_home.st.session_state", {})
    monkeypatch.setattr("ui.command_center_home.st.query_params", qp)

    return_from_auth()
    assert qp["view"] == "demo"
    assert qp["page"] == "overview"


def test_return_from_auth_rejects_auth_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {
        CC_RETURN_VIEW_KEY: "auth",
        CC_RETURN_PAGE_KEY: "overview",
    }

    class _Query(dict):
        def __setitem__(self, key: str, value: object) -> None:
            super().__setitem__(key, str(value))

    qp = _Query({"view": "auth", "page": "overview"})
    monkeypatch.setattr("ui.command_center_home.st.session_state", state)
    monkeypatch.setattr("ui.command_center_home.st.query_params", qp)

    return_from_auth()
    assert qp["view"] == "demo"
    assert qp["page"] == "overview"


def test_navigate_to_auth_keeps_existing_return_when_already_on_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        CC_RETURN_VIEW_KEY: "demo",
        CC_RETURN_PAGE_KEY: "income",
    }

    class _Query(dict):
        def __setitem__(self, key: str, value: object) -> None:
            super().__setitem__(key, str(value))

    qp = _Query({"view": "auth", "page": "overview"})
    monkeypatch.setattr("ui.command_center_home.st.session_state", state)
    monkeypatch.setattr("ui.command_center_home.st.query_params", qp)

    navigate_to_auth(source_section="nav")
    assert state[CC_RETURN_VIEW_KEY] == "demo"
    assert state[CC_RETURN_PAGE_KEY] == "income"
    assert qp["view"] == "auth"


def test_navigate_public_sets_query_and_tracks(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, object] = {}
    events: list[str] = []

    class _Query(dict):
        def __setitem__(self, key: str, value: object) -> None:
            super().__setitem__(key, str(value))

    qp = _Query()
    monkeypatch.setattr("ui.command_center_home.st.session_state", state)
    monkeypatch.setattr("ui.command_center_home.st.query_params", qp)
    monkeypatch.setattr(
        "ui.command_center_home.track_guidance_event",
        lambda name, session=None, properties=None: events.append(name),
    )

    navigate_public(
        PublicView.DEMO,
        DemoPage.INCOME,
        source_section="nav",
        analytics_event="public_demo_started",
        analytics_dedupe_key="started",
    )
    assert qp["view"] == "demo"
    assert qp["page"] == "income"
    assert events == ["public_demo_started"]


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
    # Research / Import are optional — primary journey ends at Create portfolio.
    assert resolve_next_demo_step().target_page is None
    assert resolve_next_demo_step().action_label == "Create portfolio"
