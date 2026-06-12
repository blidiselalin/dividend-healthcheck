"""Chart layout helpers — margins and axis ticks."""
# ruff: noqa: S101

from __future__ import annotations

from utils.chart_theme import (
    bottom_legend,
    evolution_chart_margins,
    monthly_category_axis,
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


def test_bottom_legend_is_centered_below_plot() -> None:
    legend = bottom_legend()
    assert legend["orientation"] == "h"
    assert legend["yanchor"] == "top"
    assert legend["y"] < 0
