"""Tests for design system helpers."""

from ui.design_system import status_class_for_label


def test_status_class_mapping() -> None:
    assert status_class_for_label("Healthy") == "healthy"
    assert status_class_for_label("Watch") == "watch"
    assert status_class_for_label("Not enough data") == "unknown"
