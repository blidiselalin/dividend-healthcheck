"""
DividendScope in-app assistant — server-side replies (no browser API keys).

Priority:
1. Curated app/portfolio FAQ (deterministic, no network)
2. Optional Hugging Face Inference API when HUGGINGFACE_API_KEY or HF_TOKEN is set
3. Safe fallback with guidance
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Hi! I'm the **DividendScope assistant**. I can explain how to use this app "
    "(holdings, yield channels, dividend sync) and general dividend concepts. "
    "I don't provide personalized investment advice."
)

DISCLAIMER = (
    "_Educational only — not financial advice. Verify data with official filings "
    "and your own research._"
)

HF_MODEL_DEFAULT = "facebook/blenderbot-400M-distill"
HF_INFERENCE_URL_TEMPLATE = "https://api-inference.huggingface.co/models/{model}"

# (keyword substrings, answer markdown)
_APP_FAQ: Sequence[Tuple[Tuple[str, ...], str]] = (
    (
        ("reload", "live data", "refresh price", "fresh price"),
        "Use **Reload live data** in the sidebar to refresh holdings prices and analysis. "
        "Use **Refresh watchlists** for a faster risk-list update without new prices.",
    ),
    (
        ("yield channel", "yield zone", "weiss", "geraldine"),
        "Open a holding or the **Holdings** tab for **Dividend Yield Channels** (Geraldine Weiss zones: "
        "green = high yield vs history, red = expensive). If a chart is missing, click **Reload live data**.",
    ),
    (
        ("add holding", "add stock", "manage portfolio", "new ticker"),
        "Go to **Manage portfolio** in the sidebar to add or edit positions, shares, and cost basis.",
    ),
    (
        ("dividend sync", "dividend receipt", "paid dividend", "cash received"),
        "Paid dividends are synced from the shared library into your journal periodically. "
        "After changing holdings, use **Reload live data** to refresh totals.",
    ),
    (
        ("cache", "slow", "first load", "loading"),
        "The first open may build rows from the shared library; later visits use a session cache. "
        "**Reload live data** forces a full refresh.",
    ),
    (
        ("s&p", "sp500", "library", "analysed stock"),
        "The shared **S&P library** powers sector stats and enrichment (Yahoo, SEC, Stooq). "
        "On the server, run ingest via `./scripts/update_cloud_docker.sh --ingest` if the library is empty.",
    ),
    (
        ("login", "sign in", "google", "account"),
        "Sign in with your Google account when auth is enabled. Portfolio data is stored per user in PostgreSQL.",
    ),
    (
        ("help", "how to use", "getting started"),
        "Start under **Manage portfolio**, then **Reload live data**. Explore **Holdings**, **Dividends**, "
        "and the dashboard tabs. Use the examples on the home page for a guided tour.",
    ),
)


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


def is_chatbot_enabled() -> bool:
    """Feature flag (default on). Set DIVIDENDSCOPE_CHATBOT_ENABLED=0 to hide UI."""
    flag = os.environ.get("DIVIDENDSCOPE_CHATBOT_ENABLED", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def huggingface_configured() -> bool:
    return bool(_huggingface_token())


def _huggingface_token() -> str:
    return (
        os.environ.get("HUGGINGFACE_API_KEY")
        or os.environ.get("HF_TOKEN")
        or ""
    ).strip()


def _huggingface_model() -> str:
    return (os.environ.get("DIVIDENDSCOPE_CHATBOT_MODEL") or HF_MODEL_DEFAULT).strip()


def build_session_context() -> str:
    """Lightweight hints from Streamlit session (no extra DB round-trips)."""
    try:
        import streamlit as st
    except Exception:
        return ""

    parts: List[str] = []
    rows = st.session_state.get("portfolio_details_rows") or []
    if rows:
        tickers = [getattr(r, "ticker", "") for r in rows[:10]]
        tickers = [t for t in tickers if t]
        if tickers:
            suffix = "…" if len(rows) > len(tickers) else ""
            parts.append(
                f"Portfolio session: {len(rows)} holdings ({', '.join(tickers)}{suffix})."
            )
    elif st.session_state.get("portfolio_fast_loaded"):
        parts.append("Portfolio session: fast-loaded from library; charts may still be loading.")

    market = st.session_state.get("market_db_status") or {}
    doc_count = int(market.get("document_count") or 0)
    if doc_count > 0:
        parts.append(f"Shared market library: {doc_count} analysed tickers.")

    return " ".join(parts)


def match_local_faq(message: str) -> Optional[str]:
    """Return a curated answer when the user asks about app features."""
    text = (message or "").strip().lower()
    if not text:
        return None
    for keywords, answer in _APP_FAQ:
        if any(keyword in text for keyword in keywords):
            return answer
    return None


def _pair_conversation_history(
    messages: Sequence[ChatMessage],
) -> Tuple[List[str], List[str]]:
    """Build BlenderBot past_user_inputs / generated_responses from chat history."""
    past_user: List[str] = []
    past_bot: List[str] = []
    seen_user = False
    for msg in messages:
        if msg.role == "user":
            seen_user = True
            past_user.append(msg.content)
        elif msg.role == "assistant":
            if msg.content == WELCOME_MESSAGE or not seen_user:
                continue
            past_bot.append(msg.content)
    # BlenderBot expects equal-length prior turns; trim to last 3 exchanges
    while len(past_bot) < len(past_user) - 1:
        past_bot.insert(0, "")
    while len(past_user) > len(past_bot) + 1:
        past_user.pop(0)
        if past_bot:
            past_bot.pop(0)
    past_user = past_user[:-1][-3:]
    past_bot = past_bot[-3:]
    return past_user, past_bot


def reply_via_huggingface(
    user_message: str,
    messages: Sequence[ChatMessage],
    *,
    token: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 25,
) -> Optional[str]:
    """
    Call Hugging Face Inference API from the server (avoids browser CORS and exposes no token).
    """
    api_token = token or _huggingface_token()
    if not api_token:
        return None

    try:
        import requests
    except ImportError:
        logger.warning("requests not installed; skipping Hugging Face chat")
        return None

    model_id = model or _huggingface_model()
    url = HF_INFERENCE_URL_TEMPLATE.format(model=model_id)
    past_user, past_bot = _pair_conversation_history(messages)

    payload = {
        "inputs": {
            "past_user_inputs": past_user,
            "generated_responses": past_bot,
            "text": user_message,
        }
    }
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning("Hugging Face chat request failed: %s", exc)
        return None

    if response.status_code == 503:
        return "The language model is warming up. Please try again in a few seconds."

    if not response.ok:
        logger.debug(
            "Hugging Face chat HTTP %s: %s",
            response.status_code,
            response.text[:200],
        )
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if isinstance(data, dict):
        generated = data.get("generated_text") or data.get("conversation", {}).get(
            "generated_responses"
        )
        if isinstance(generated, list) and generated:
            return str(generated[-1]).strip()
        if isinstance(generated, str) and generated.strip():
            return generated.strip()
    elif isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and first.get("generated_text"):
            return str(first["generated_text"]).strip()

    return None


def fallback_reply(user_message: str, *, session_context: str = "") -> str:
    """Default when FAQ and optional LLM do not apply."""
    lines = [
        "I didn't find a specific app answer for that.",
        "Try asking about **Reload live data**, **yield channels**, **Manage portfolio**, or **dividend sync**.",
    ]
    if session_context:
        lines.append(f"_{session_context}_")
    if not huggingface_configured():
        lines.append(
            "_Tip: set `HUGGINGFACE_API_KEY` on the server for broader conversational replies._"
        )
    lines.append(DISCLAIMER)
    return "\n\n".join(lines)


def generate_reply(user_message: str, messages: Sequence[ChatMessage]) -> str:
    """
    Produce the assistant reply for a user turn.

    App FAQ answers are preferred so help stays accurate; optional HF fills general chat.
    """
    text = (user_message or "").strip()
    if not text:
        return "Please enter a message."

    local = match_local_faq(text)
    if local:
        ctx = build_session_context()
        if ctx:
            return f"{local}\n\n_{ctx}_\n\n{DISCLAIMER}"
        return f"{local}\n\n{DISCLAIMER}"

    session_context = build_session_context()
    if len(text) < 120 and session_context:
        # Short general questions still benefit from session hint before LLM
        pass

    llm_reply = reply_via_huggingface(text, messages)
    if llm_reply:
        return f"{llm_reply}\n\n{DISCLAIMER}"

    return fallback_reply(text, session_context=session_context)


def initial_messages() -> List[Dict[str, str]]:
    """Default chat history for st.session_state."""
    return [{"role": "assistant", "content": WELCOME_MESSAGE}]
