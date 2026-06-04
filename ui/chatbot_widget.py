"""
In-app assistant — Streamlit sidebar chat (server-side replies).

Uses st.chat_message with a text form for input (no microphone / WaveSurfer UI).
"""

from __future__ import annotations

import logging

import streamlit as st

from services.chatbot_service import (
    ChatMessage,
    WELCOME_MESSAGE,
    generate_reply,
    initial_messages,
    is_chatbot_enabled,
    huggingface_configured,
)

logger = logging.getLogger(__name__)

SESSION_MESSAGES_KEY = "chat_messages"
CHAT_FORM_KEY = "ds_assistant_form"
CHAT_TEXT_KEY = "ds_assistant_text"

ERROR_REPLY = (
    "Sorry, something went wrong while generating a reply. "
    "Please try again or ask about **Reload live data**, **yield channels**, or **Manage portfolio**."
)


def _init_chat_state() -> None:
    if SESSION_MESSAGES_KEY not in st.session_state:
        st.session_state[SESSION_MESSAGES_KEY] = initial_messages()


def _append_message(role: str, content: str) -> None:
    st.session_state[SESSION_MESSAGES_KEY].append(
        {"role": role, "content": content}
    )


def _render_chat_messages() -> None:
    messages = st.session_state.get(SESSION_MESSAGES_KEY) or []
    skip_welcome_duplicate = len(messages) > 1
    for msg in messages:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        if (
            skip_welcome_duplicate
            and role == "assistant"
            and content == WELCOME_MESSAGE
        ):
            continue
        with st.chat_message(role):
            st.markdown(content)


def _handle_user_prompt(prompt: str) -> None:
    text = prompt.strip()
    if not text:
        return

    _append_message("user", text)
    history = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in st.session_state[SESSION_MESSAGES_KEY][:-1]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    show_hf_tip = not st.session_state.get("chat_assistant_hf_tip_shown")
    try:
        reply = generate_reply(text, history, show_hf_tip_on_fallback=show_hf_tip)
        if show_hf_tip and "HUGGINGFACE_API_KEY" in reply:
            st.session_state["chat_assistant_hf_tip_shown"] = True
    except Exception as exc:
        logger.warning("Assistant reply failed: %s", exc, exc_info=True)
        reply = ERROR_REPLY
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

    with st.sidebar.form(CHAT_FORM_KEY, clear_on_submit=True):
        prompt = st.text_input(
            "Message",
            placeholder="Ask about the app or dividends…",
            key=CHAT_TEXT_KEY,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Send", use_container_width=True)

    if submitted and prompt and str(prompt).strip():
        _handle_user_prompt(str(prompt))
        st.rerun()
