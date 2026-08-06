"""Unit tests for Command Center public routing."""
# ruff: noqa: S101

from __future__ import annotations

import pytest

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
