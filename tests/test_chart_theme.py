"""Chart layout helpers — margins and axis ticks."""
# ruff: noqa: S101

from __future__ import annotations

from utils.chart_theme import (
    DARK_PALETTE,
    bottom_legend,
    evolution_chart_margins,
    monthly_category_axis,
    style_yield_channel_figure,
    yield_zone_fill,
)


def test_evolution_chart_margins_grow_with_categories_and_legend() -> None:
    base = evolution_chart_margins(6)
    many = evolution_chart_margins(20)
    with_legend = evolution_chart_margins(6, legend_bottom=True)

    assert many["b"] > base["b"]
    assert with_legend["b"] > base["b"]
    assert with_legend["t"] == 40


def test_evolution_chart_dual_y_increases_right_margin() -> None:
    single = evolution_chart_margins(8)
    dual = evolution_chart_margins(8, dual_y=True)
    assert dual["r"] > single["r"]


def test_monthly_category_axis_rotates_long_histories() -> None:
    short = monthly_category_axis(4)
    long = monthly_category_axis(24)
    assert short["tickangle"] == 0
    assert long["tickangle"] == -55
    assert long["nticks"] <= 12


def test_style_yield_channel_figure_uses_dark_palette() -> None:
    import plotly.graph_objects as go

    fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[1, 2])])
    styled = style_yield_channel_figure(fig, height=400)
    assert styled.layout.paper_bgcolor == DARK_PALETTE["paper"]
    assert styled.layout.plot_bgcolor == DARK_PALETTE["plot"]


def test_yield_zone_fill_returns_rgba() -> None:
    fill = yield_zone_fill("Value", alpha=0.2)
    assert fill.startswith("rgba(")
    assert "74" in fill or "222" in fill  # green channel from #4ade80
