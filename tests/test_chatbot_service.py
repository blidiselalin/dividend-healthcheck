"""Tests for the in-app assistant service."""
# ruff: noqa: S101

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.chatbot_service import (
    WELCOME_MESSAGE,
    ChatMessage,
    SessionPortfolioSnapshot,
    _bot_turn_for_history,
    _pair_conversation_history,
    build_session_context,
    coerce_chat_prompt,
    format_assistant_reply,
    generate_reply,
    huggingface_configured,
    is_chatbot_enabled,
    match_local_faq,
    match_session_reply,
    reply_via_huggingface,
)


def test_chatbot_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIVIDENDSCOPE_CHATBOT_ENABLED", raising=False)
    assert is_chatbot_enabled() is True


def test_chatbot_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIVIDENDSCOPE_CHATBOT_ENABLED", "0")
    assert is_chatbot_enabled() is False


def test_match_local_faq_reload() -> None:
    answer = match_local_faq("How do I reload live data?")
    assert answer is not None
    assert "Reload live data" in answer


def test_match_local_faq_yield_channel() -> None:
    answer = match_local_faq("Explain yield channels")
    assert answer is not None
    assert "Yield" in answer or "yield" in answer


def test_generate_reply_uses_faq_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    reply = generate_reply("reload portfolio prices", [])
    assert "Reload live data" in reply
    assert "not financial advice" in reply.lower() or "Educational" in reply


def test_generate_reply_fallback_without_hf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    reply = generate_reply("quantum physics entanglement", [], show_hf_tip_on_fallback=True)
    assert "didn't match" in reply.lower()
    assert "HUGGINGFACE" in reply


def test_generate_reply_fallback_no_hf_tip_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    reply = generate_reply("quantum physics entanglement", [])
    assert "HUGGINGFACE" not in reply


def test_match_session_reply_portfolio() -> None:
    import services.chatbot_service as mod

    snap = SessionPortfolioSnapshot(2, ("ABBV", "KO"), 510)
    original = mod._session_portfolio_snapshot
    mod._session_portfolio_snapshot = lambda: snap
    try:
        answer = match_session_reply("what is in my portfolio?")
        assert answer is not None
        assert "2" in answer and "ABBV" in answer
    finally:
        mod._session_portfolio_snapshot = original


def test_match_session_reply_ticker() -> None:
    snap = SessionPortfolioSnapshot(46, ("ABBV", "ADM"), 510)
    import services.chatbot_service as mod

    original = mod._session_portfolio_snapshot
    mod._session_portfolio_snapshot = lambda: snap
    try:
        answer = match_session_reply("tell me about ABBV yield")
        assert answer is not None
        assert "ABBV" in answer
        assert "yield" in answer.lower()
    finally:
        mod._session_portfolio_snapshot = original


def test_pair_conversation_history_aligns_turns() -> None:
    messages = [
        ChatMessage("assistant", "Welcome"),
        ChatMessage("user", "Hi"),
        ChatMessage("assistant", "Hello"),
        ChatMessage("user", "What is KO?"),
    ]
    past_user, past_bot = _pair_conversation_history(messages)
    assert past_user == ["Hi"]
    assert past_bot == ["Hello"]


@patch("requests.post")
def test_reply_via_huggingface_success(mock_post: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "test-token")
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.status_code = 200
    mock_response.json.return_value = {"generated_text": "Dividends can signal value."}
    mock_post.return_value = mock_response

    reply = reply_via_huggingface(
        "Tell me about dividends",
        [ChatMessage("user", "Hi")],
        token="test-token",  # noqa: S106
    )
    assert reply == "Dividends can signal value."
    mock_post.assert_called_once()
    _args, kwargs = mock_post.call_args
    headers = kwargs.get("headers") or {}
    assert headers["Authorization"] == "Bearer test-token"


def test_huggingface_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "x")
    assert huggingface_configured() is True


def test_build_session_context_without_streamlit() -> None:
    assert build_session_context() == ""


def test_coerce_chat_prompt_string_and_dict() -> None:
    assert coerce_chat_prompt("  hello  ") == "hello"
    assert coerce_chat_prompt({"text": "yield zones"}) == "yield zones"
    assert coerce_chat_prompt(None) == ""


def test_bot_turn_for_history_strips_disclaimer() -> None:
    from services.chatbot_service import DISCLAIMER

    raw = f"Use Reload live data.\n\n{DISCLAIMER}"
    assert _bot_turn_for_history(raw) == "Use Reload live data."
    assert _bot_turn_for_history(WELCOME_MESSAGE) == ""


def test_pair_conversation_skips_welcome_message() -> None:
    from services.chatbot_service import DISCLAIMER

    messages = [
        ChatMessage("assistant", WELCOME_MESSAGE),
        ChatMessage("user", "Hi"),
        ChatMessage("assistant", f"Hello there.\n\n{DISCLAIMER}"),
        ChatMessage("user", "Thanks"),
    ]
    past_user, past_bot = _pair_conversation_history(messages)
    assert past_user == ["Hi"]
    assert past_bot == ["Hello there."]


def test_generate_reply_empty_message() -> None:
    reply = generate_reply("   ", [])
    assert "enter a message" in reply.lower()


def test_format_assistant_reply_includes_disclaimer() -> None:
    text = format_assistant_reply("Hello", show_hf_tip=False)
    assert "Educational only" in text
    assert "Hello" in text
