"""Tests for design system helpers."""

from ui.design_system import (
    _data_provenance_markup,
    _demo_progress_markup,
    _empty_state_markup,
    _metric_card_markup,
    _metric_grid_markup,
    _page_header_markup,
    get_design_system_css,
    looks_negative_display,
    render_metric_grid,
    status_class_for_label,
)
from ui.theme_mode import THEME_DARK, THEME_LIGHT, theme_tokens


def test_status_class_mapping() -> None:
    assert status_class_for_label("Healthy") == "healthy"
    assert status_class_for_label("Watch") == "watch"
    assert status_class_for_label("Not enough data") == "unknown"
    assert status_class_for_label("Confirmed") == "confirmed"
    assert status_class_for_label("Estimated") == "estimated"
    assert status_class_for_label("Lower observed risk") == "healthy"
    assert status_class_for_label("High observed risk") == "risky"
    assert status_class_for_label("Special analysis required") == "unknown"


def test_metric_markup_uses_highlight_class() -> None:
    card = _metric_card_markup("Yield", "3.2%", "vs median", highlight=True)
    assert "ds-metric-card ds-highlight" in card
    assert "3.2%" in card


def test_looks_negative_display_detects_signed_values() -> None:
    assert looks_negative_display("$-1,234.56")
    assert looks_negative_display("-$50.00")
    assert looks_negative_display("-1.25%")
    assert looks_negative_display("−3.1%")  # unicode minus
    assert not looks_negative_display("+$50.00")
    assert not looks_negative_display("+1.25%")
    assert not looks_negative_display("$1,234.56")
    assert not looks_negative_display("Reload live data")


def test_metric_markup_marks_negative_values() -> None:
    card = _metric_card_markup("Day change", "$-120.00", "-1.25%", highlight=True)
    assert "ds-metric-negative" in card
    assert "ds-metric-value ds-neg" in card
    assert "ds-metric-hint ds-neg" in card
    positive = _metric_card_markup("Day change", "$+120.00", "+1.25%")
    assert "ds-metric-negative" not in positive
    assert "ds-neg" not in positive


def test_metric_markup_escapes_dynamic_text() -> None:
    card = _metric_card_markup("<b>Label</b>", "<script>1</script>", 'hint&"x"')
    assert "<b>Label</b>" not in card
    assert "<script>" not in card
    assert "&lt;b&gt;Label&lt;/b&gt;" in card
    assert "&lt;script&gt;1&lt;/script&gt;" in card
    assert "hint&amp;&quot;x&quot;" in card


def test_metric_grid_is_compact_single_block() -> None:
    grid = _metric_grid_markup([("Income", "$100", "hint", True)])
    assert grid.startswith('<div class="ds-metric-grid">')
    assert "\n        " not in grid


def test_metric_strip_class_on_home_grid() -> None:
    strip = _metric_grid_markup([("Value", "$1", "open")], strip=True)
    assert 'class="ds-metric-grid ds-metric-strip"' in strip


def test_page_header_markup_hierarchy_and_escaping() -> None:
    html = _page_header_markup(
        "Overview <x>",
        'Sub "quote"',
        kicker="Home & more",
    )
    assert 'class="ds-page-header"' in html
    assert 'class="ds-page-title"' in html
    assert "Overview &lt;x&gt;" in html
    assert "Home &amp; more" in html
    assert "Sub &quot;quote&quot;" in html
    assert "<x>" not in html


def test_empty_state_markup_escapes_and_surfaces() -> None:
    html = _empty_state_markup("No <rows>", "Add & review", icon="<i>")
    assert "ds-empty-state" in html
    assert "ds-surface-card" in html
    assert "No &lt;rows&gt;" in html
    assert "Add &amp; review" in html
    assert "&lt;i&gt;" in html


def test_data_provenance_escapes() -> None:
    html = _data_provenance_markup('Prices <live> & "lib"')
    assert "ds-provenance" in html
    assert "&lt;live&gt;" in html
    assert "&amp;" in html


def test_dark_design_system_css_styles_buttons_and_segmented_control() -> None:
    css = get_design_system_css(theme=THEME_DARK)
    assert "--ds-btn-text: #e8eef7" in css
    assert "stBaseButton-secondary" in css
    assert "stSegmentedControl" in css
    assert "var(--ds-btn-primary-text)" in css
    assert "ds-portfolio-nav-section" in css
    assert "--ds-content-width:" in css
    assert ".ds-page-header" in css
    assert "var(--ds-focus)" in css
    assert ".ds-metric-negative" in css
    assert ".ds-neg" in css


def test_light_design_system_css_uses_dark_button_text() -> None:
    css = get_design_system_css(theme=THEME_LIGHT)
    assert "--ds-btn-text: #0f172a" in css
    assert "--ds-btn-bg: #ffffff" in css
    assert "--ds-content-width:" in css
    assert "--ds-healthy:" in css
    assert "--ds-warning:" in css
    assert "--ds-risk:" in css


def test_theme_tokens_include_launch_scale() -> None:
    for mode in (THEME_DARK, THEME_LIGHT):
        tokens = theme_tokens(mode)
        assert tokens["radius-sm"] == "10px"
        assert tokens["radius"] == "14px"
        assert tokens["radius-md"] == "14px"
        assert tokens["radius-lg"] == "18px"
        assert tokens["radius-pill"] == "999px"
        assert tokens["space-1"] == "4px"
        assert tokens["space-8"] == "64px"
        assert tokens["content-width"] == "1200px"
        assert tokens["primary-hover"] == "#14b8a6"
        assert tokens["healthy"]
        assert tokens["success"] == tokens["healthy"]
        assert tokens["confirmed"]
        assert tokens["estimated"]
        assert tokens["surface-highlight"]
        assert tokens["surface-high"]
        assert tokens["text-muted"] == tokens["muted"]
        assert tokens["shadow-card"]


def test_demo_progress_markup_states_and_escaping() -> None:
    html = _demo_progress_markup(
        ["Import <x>", "Verify", "Research"],
        active_index=1,
    )
    assert 'class="ds-demo-progress"' in html
    assert 'data-state="done"' in html
    assert 'data-state="active"' in html
    assert 'data-state="todo"' in html
    assert "Import &lt;x&gt;" in html
    assert "<x>" not in html


def test_mobile_safe_layout_classes_present() -> None:
    css = get_design_system_css(theme=THEME_DARK)
    assert ".ds-demo-progress" in css
    assert ".ds-feature-grid" in css
    assert "min-width: 0" in css
    assert ".cc-hero-title" in css


def test_render_metric_grid_helper_still_available() -> None:
    # Backward compatibility: public helper remains importable / callable.
    assert callable(render_metric_grid)
