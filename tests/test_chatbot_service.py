"""Tests for the in-app assistant service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.chatbot_service import (
    WELCOME_MESSAGE,
    ChatMessage,
    build_session_context,
    coerce_chat_prompt,
    generate_reply,
    huggingface_configured,
    is_chatbot_enabled,
    match_local_faq,
    reply_via_huggingface,
    _bot_turn_for_history,
    _pair_conversation_history,
)


def test_chatbot_enabled_by_default(monkeypatch):
    monkeypatch.delenv("DIVIDENDSCOPE_CHATBOT_ENABLED", raising=False)
    assert is_chatbot_enabled() is True


def test_chatbot_disabled_via_env(monkeypatch):
    monkeypatch.setenv("DIVIDENDSCOPE_CHATBOT_ENABLED", "0")
    assert is_chatbot_enabled() is False


def test_match_local_faq_reload():
    answer = match_local_faq("How do I reload live data?")
    assert answer is not None
    assert "Reload live data" in answer


def test_match_local_faq_yield_channel():
    answer = match_local_faq("Explain yield channels")
    assert answer is not None
    assert "Yield" in answer or "yield" in answer


def test_generate_reply_uses_faq_without_network(monkeypatch):
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    reply = generate_reply("reload portfolio prices", [])
    assert "Reload live data" in reply
    assert "not financial advice" in reply.lower() or "Educational" in reply


def test_generate_reply_fallback_without_hf(monkeypatch):
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    reply = generate_reply("quantum physics entanglement", [])
    assert "didn't find" in reply.lower() or "HUGGINGFACE" in reply


def test_pair_conversation_history_aligns_turns():
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
def test_reply_via_huggingface_success(mock_post, monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "test-token")
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.status_code = 200
    mock_response.json.return_value = {"generated_text": "Dividends can signal value."}
    mock_post.return_value = mock_response

    reply = reply_via_huggingface(
        "Tell me about dividends",
        [ChatMessage("user", "Hi")],
        token="test-token",
    )
    assert reply == "Dividends can signal value."
    mock_post.assert_called_once()
    _args, kwargs = mock_post.call_args
    headers = kwargs.get("headers") or {}
    assert headers["Authorization"] == "Bearer test-token"


def test_huggingface_configured(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "x")
    assert huggingface_configured() is True


def test_build_session_context_without_streamlit():
    assert build_session_context() == ""


def test_coerce_chat_prompt_string_and_dict():
    assert coerce_chat_prompt("  hello  ") == "hello"
    assert coerce_chat_prompt({"text": "yield zones"}) == "yield zones"
    assert coerce_chat_prompt(None) == ""


def test_bot_turn_for_history_strips_disclaimer():
    from services.chatbot_service import DISCLAIMER

    raw = f"Use Reload live data.\n\n{DISCLAIMER}"
    assert _bot_turn_for_history(raw) == "Use Reload live data."
    assert _bot_turn_for_history(WELCOME_MESSAGE) == ""


def test_pair_conversation_skips_welcome_message():
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


def test_generate_reply_empty_message():
    reply = generate_reply("   ", [])
    assert "enter a message" in reply.lower()
