"""Theme mode helpers."""

from ui.theme_mode import (
    THEME_DARK,
    THEME_LIGHT,
    build_theme_root_css,
    normalize_theme,
    theme_tokens,
)


def test_normalize_theme_defaults_to_dark() -> None:
    assert normalize_theme(None) == THEME_DARK
    assert normalize_theme("dark") == THEME_DARK
    assert normalize_theme("Light") == THEME_LIGHT


def test_theme_tokens_include_button_vars() -> None:
    dark = theme_tokens(THEME_DARK)
    light = theme_tokens(THEME_LIGHT)
    assert dark["btn-bg"] != light["btn-bg"]
    assert "--ds-btn-bg" in build_theme_root_css(THEME_DARK)
