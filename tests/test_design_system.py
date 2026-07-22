"""Tests for design system helpers."""

from ui.design_system import (
    _metric_card_markup,
    _metric_grid_markup,
    get_design_system_css,
    status_class_for_label,
)
from ui.theme_mode import THEME_DARK, THEME_LIGHT


def test_status_class_mapping() -> None:
    assert status_class_for_label("Healthy") == "healthy"
    assert status_class_for_label("Watch") == "watch"
    assert status_class_for_label("Not enough data") == "unknown"


def test_metric_markup_uses_highlight_class() -> None:
    card = _metric_card_markup("Yield", "3.2%", "vs median", highlight=True)
    assert "ds-metric-card ds-highlight" in card
    assert "3.2%" in card


def test_metric_grid_is_compact_single_block() -> None:
    grid = _metric_grid_markup([("Income", "$100", "hint", True)])
    assert grid.startswith('<div class="ds-metric-grid">')
    assert "\n        " not in grid


def test_dark_design_system_css_styles_buttons_and_segmented_control() -> None:
    css = get_design_system_css(theme=THEME_DARK)
    assert "--ds-btn-text: #e8eef7" in css
    assert "stBaseButton-secondary" in css
    assert "stSegmentedControl" in css
    assert "var(--ds-btn-primary-text)" in css
    assert "ds-portfolio-nav-section" in css


def test_light_design_system_css_uses_dark_button_text() -> None:
    css = get_design_system_css(theme=THEME_LIGHT)
    assert "--ds-btn-text: #0f172a" in css
    assert "--ds-btn-bg: #ffffff" in css
