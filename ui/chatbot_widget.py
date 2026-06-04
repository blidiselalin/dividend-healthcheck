"""
In-app assistant — Streamlit sidebar chat (server-side replies).

Uses st.chat_message / st.chat_input with session state. Avoids embedding
third-party API keys in the browser (CORS and security issues with components.html).
"""

from __future__ import annotations

import streamlit as st

from services.chatbot_service import (
    WELCOME_MESSAGE,
    generate_reply,
    initial_messages,
    is_chatbot_enabled,
    huggingface_configured,
)

SESSION_MESSAGES_KEY = "chat_messages"
CHAT_INPUT_KEY = "ds_assistant_chat_input"


def _init_chat_state() -> None:
    if SESSION_MESSAGES_KEY not in st.session_state:
        st.session_state[SESSION_MESSAGES_KEY] = initial_messages()


def _append_message(role: str, content: str) -> None:
    st.session_state[SESSION_MESSAGES_KEY].append(
        {"role": role, "content": content}
    )


def _render_chat_messages() -> None:
    for msg in st.session_state[SESSION_MESSAGES_KEY]:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        if role == "assistant" and content == WELCOME_MESSAGE and len(
            st.session_state[SESSION_MESSAGES_KEY]
        ) > 1:
            pass
        with st.chat_message(role):
            st.markdown(content)


def _coerce_chat_prompt(raw: object) -> str:
    """Normalize st.chat_input return value (str or multimodal dict)."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        return str(raw.get("text") or "").strip()
    text = getattr(raw, "text", None)
    if text is not None:
        return str(text).strip()
    return str(raw).strip()


def _sidebar_chat_input(placeholder: str, *, key: str) -> object:
    """
    Sidebar chat input without audio recording (avoids WaveSurfer container errors
    when the widget is inside a collapsed expander).
    """
    try:
        return st.sidebar.chat_input(
            placeholder,
            key=key,
            accept_audio=False,
        )
    except TypeError:
        # Streamlit < 1.40 without accept_audio
        return st.sidebar.chat_input(placeholder, key=key)


def _handle_user_prompt(prompt: str) -> None:
    from services.chatbot_service import ChatMessage

    text = prompt.strip()
    if not text:
        return

    _append_message("user", text)
    history = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in st.session_state[SESSION_MESSAGES_KEY][:-1]
    ]
    reply = generate_reply(text, history)
    _append_message("assistant", reply)


def render_chatbot_widget() -> None:
    """
    Sidebar assistant panel — call from main() after other sidebar sections.

    Hidden when DIVIDENDSCOPE_CHATBOT_ENABLED=0.
    """
    if not is_chatbot_enabled():
        return

    _init_chat_state()

    st.sidebar.divider()
    hf_note = " · AI replies enabled" if huggingface_configured() else " · FAQ mode"
    with st.sidebar.expander(f"Assistant{hf_note}", expanded=False):
        _render_chat_messages()
        if st.button("Clear chat", use_container_width=True, key="ds_chat_clear"):
            st.session_state[SESSION_MESSAGES_KEY] = initial_messages()
            st.rerun()

    # Input lives outside the expander so Streamlit's audio UI (WaveSurfer) always
    # has a stable DOM container; accept_audio=False disables recording entirely.
    raw_prompt = _sidebar_chat_input(
        "Ask about the app or dividends…",
        key=CHAT_INPUT_KEY,
    )
    prompt = _coerce_chat_prompt(raw_prompt)
    if prompt:
        _handle_user_prompt(prompt)
        st.rerun()
