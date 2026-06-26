"""Tests for design system helpers."""

from ui.design_system import (
    _metric_card_markup,
    _metric_grid_markup,
    status_class_for_label,
)


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
