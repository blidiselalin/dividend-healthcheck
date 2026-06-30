"""Light / dark appearance for DividendScope."""

from __future__ import annotations

import streamlit as st

THEME_SESSION_KEY = "ds_theme_mode"
THEME_DARK = "dark"
THEME_LIGHT = "light"
THEME_LABELS = ("Dark", "Light")


def normalize_theme(value: str | None) -> str:
    if (value or "").lower() == THEME_LIGHT:
        return THEME_LIGHT
    return THEME_DARK


def init_theme_mode() -> str:
    if THEME_SESSION_KEY not in st.session_state:
        st.session_state[THEME_SESSION_KEY] = THEME_DARK
    return normalize_theme(st.session_state[THEME_SESSION_KEY])


def get_theme_mode() -> str:
    return init_theme_mode()


def set_theme_mode(mode: str) -> None:
    st.session_state[THEME_SESSION_KEY] = normalize_theme(mode)


def theme_label(mode: str | None = None) -> str:
    return "Light" if normalize_theme(mode or get_theme_mode()) == THEME_LIGHT else "Dark"


def theme_tokens(mode: str) -> dict[str, str]:
    """CSS custom property values (suffix after --ds-)."""
    shared = {
        "primary": "#2dd4bf",
        "primary-dark": "#14b8a6",
        "primary-light": "#5eead4",
        "accent": "#38bdf8",
        "radius": "12px",
        "radius-sm": "8px",
        "focus": "0 0 0 3px rgba(45, 212, 191, 0.4)",
    }
    if normalize_theme(mode) == THEME_LIGHT:
        return {
            **shared,
            "bg": "#f1f5f9",
            "bg-elevated": "#ffffff",
            "surface": "#ffffff",
            "surface-elevated": "#f8fafc",
            "border": "#cbd5e1",
            "border-subtle": "#e2e8f0",
            "text": "#0f172a",
            "muted": "#64748b",
            "highlight-bg": "rgba(45, 212, 191, 0.08)",
            "highlight-border": "rgba(13, 148, 136, 0.45)",
            "highlight-glow": "0 0 0 1px rgba(13, 148, 136, 0.2), 0 8px 24px rgba(13, 148, 136, 0.1)",
            "shadow": "0 1px 2px rgba(15, 23, 42, 0.06), 0 4px 14px rgba(15, 23, 42, 0.06)",
            "shadow-lg": "0 10px 28px rgba(15, 23, 42, 0.1)",
            "app-gradient": "linear-gradient(180deg, #e2e8f0 0%, var(--ds-bg) 140px, var(--ds-bg) 100%)",
            "btn-bg": "#ffffff",
            "btn-bg-hover": "#f1f5f9",
            "btn-text": "#0f172a",
            "btn-border": "#94a3b8",
            "btn-border-hover": "#64748b",
            "btn-primary-text": "#042f2e",
            "btn-shadow": "0 1px 2px rgba(15, 23, 42, 0.08)",
            "chart-paper": "#ffffff",
            "chart-plot": "#f8fafc",
            "chart-grid": "rgba(148, 163, 184, 0.35)",
        }
    return {
        **shared,
        "bg": "#0b1220",
        "bg-elevated": "#0f172a",
        "surface": "#131c2e",
        "surface-elevated": "#1a2740",
        "border": "#2a3a52",
        "border-subtle": "#1e293b",
        "text": "#e8eef7",
        "muted": "#94a3b8",
        "highlight-bg": "rgba(45, 212, 191, 0.1)",
        "highlight-border": "rgba(45, 212, 191, 0.5)",
        "highlight-glow": "0 0 0 1px rgba(45, 212, 191, 0.25), 0 8px 28px rgba(45, 212, 191, 0.12)",
        "shadow": "0 1px 3px rgba(0, 0, 0, 0.35), 0 4px 18px rgba(0, 0, 0, 0.25)",
        "shadow-lg": "0 10px 36px rgba(0, 0, 0, 0.45)",
        "app-gradient": "linear-gradient(180deg, #070d18 0%, var(--ds-bg) 160px, var(--ds-bg) 100%)",
        "btn-bg": "#1a2740",
        "btn-bg-hover": "#243452",
        "btn-text": "#e8eef7",
        "btn-border": "#3d5270",
        "btn-border-hover": "#4a6282",
        "btn-primary-text": "#042f2e",
        "btn-shadow": "0 1px 3px rgba(0, 0, 0, 0.35)",
        "chart-paper": "#131c2e",
        "chart-plot": "#0f172a",
        "chart-grid": "rgba(148, 163, 184, 0.14)",
    }


def build_theme_root_css(mode: str) -> str:
    tokens = theme_tokens(mode)
    body = "\n".join(f"  --ds-{key}: {value};" for key, value in tokens.items())
    return f":root {{\n{body}\n}}\n"


def render_theme_toggle(*, sidebar: bool = False) -> None:
    """Segmented control to switch light / dark appearance."""
    ui = st.sidebar if sidebar else st
    current = get_theme_mode()
    with ui:
        choice = st.segmented_control(
            "Theme",
            options=list(THEME_LABELS),
            default=theme_label(current),
            key=f"ds_theme_toggle_{'sidebar' if sidebar else 'main'}",
            label_visibility="collapsed",
            help="Switch between dark and light appearance",
        )
    selected = normalize_theme(str(choice).lower() if choice else current)
    if selected != current:
        set_theme_mode(selected)
        st.rerun()
