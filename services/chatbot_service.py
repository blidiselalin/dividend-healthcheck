"""
DividendScope in-app assistant — server-side replies (no browser API keys).

Priority:
1. Curated app/portfolio FAQ (deterministic, no network)
2. Session-aware answers (holdings loaded, ticker mentions)
3. Optional Hugging Face Inference API when HUGGINGFACE_API_KEY or HF_TOKEN is set
4. Short fallback with examples (no repeated HF tip every turn)
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Hi! I'm the **DividendScope assistant**. New here? On Home, open **Getting started — step-by-step guide**. "
    "Ask how to use the app, name a ticker (e.g. **ABBV**), or try: *reload live data*, *yield channels*, "
    "*my portfolio*. I explain features and concepts — not personalized buy/sell advice."
)

DISCLAIMER = (
    "_Educational only — not financial advice. Verify data with official filings "
    "and your own research._"
)

HF_MODEL_DEFAULT = "facebook/blenderbot-400M-distill"
HF_INFERENCE_URL_TEMPLATE = "https://api-inference.huggingface.co/models/{model}"

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")

# (keyword substrings, answer markdown)
_APP_FAQ: Sequence[tuple[tuple[str, ...], str]] = (
    (
        ("reload", "live data", "refresh price", "fresh price"),
        "Use **Reload live data** in the sidebar to queue a **background** refresh of prices, "
        "yield charts, and watchlists. Progress appears under **Background tasks**. "
        "Use **Refresh watchlists** for a faster risk-list update without new prices.",
    ),
    (
        ("yield channel", "yield zone", "weiss", "geraldine"),
        "Open a holding or the **Holdings** tab for **Dividend Yield Channels** (Geraldine "
        "Weiss zones: green = high yield vs history, red = expensive). If a chart is "
        "missing, click **Reload live data**.",
    ),
    (
        ("add holding", "add stock", "manage portfolio", "new ticker"),
        "Go to **Manage portfolio** in the sidebar → **Add ticker** (symbol, shares, cost). "
        "Views update in the **background** after you save — watch **Background tasks**. "
        "Then use **Reload live data** for today's prices and charts.",
    ),
    (
        ("dividend sync", "dividend receipt", "paid dividend", "cash received"),
        "Paid dividends are synced from the shared library into your journal periodically. "
        "After changing holdings, wait for the background update or use **Reload live data**.",
    ),
    (
        ("cache", "slow", "first load", "loading", "background"),
        "Heavy work runs in **Background tasks** (sidebar) so the UI stays responsive. "
        "The first visit may warm holdings from the shared library; later visits use a disk cache. "
        "**Reload live data** queues a full live refresh in the background.",
    ),
    (
        ("s&p", "sp500", "library", "analysed stock"),
        "The shared **S&P library** powers sector stats and enrichment (Yahoo, SEC, "
        "Stooq). On the server, run ingest via `./scripts/update_cloud_docker.sh "
        "--ingest` if the library is empty.",
    ),
    (
        ("login", "sign in", "google", "account"),
        "Sign in with your Google account when auth is enabled. Portfolio data is "
        "stored per user in PostgreSQL.",
    ),
    (
        ("help", "how to use", "getting started", "onboarding", "new user"),
        "Open **Getting started — step-by-step guide** on Home (4 steps): "
        "**Manage portfolio** → wait for **Background tasks** → **Reload live data** → "
        "explore **Holdings** / **Dividend income**. Expand **What is DividendScope?** for "
        "what each section contains.",
    ),
    (
        ("risk", "watchlist", "attention", "buy zone"),
        "After **Reload live data** (background job), check **Portfolio risks** in the sidebar. "
        "**Refresh watchlists** rescans from cached rows without new prices. Yield zones on "
        "**Holdings** show green (historically high yield) vs red (expensive).",
    ),
    (
        ("dividend yield", "what is yield", "yield mean"),
        "**Dividend yield** = annual dividend per share ÷ price. In this app, yield "
        "**channels** compare today's yield to the stock's own history to spot "
        "relatively cheap or rich prices — not a buy signal alone.",
    ),
    (
        ("dashboard", "overview", "performance", "home"),
        "**Home** shows value, P/L, month dividends received, and a positions table. "
        "**Deposits & benchmarks** tracks capital deposited and index comparison. "
        "If numbers are empty, finish **Getting started** on Home or wait for **Background tasks**.",
    ),
)


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class SessionPortfolioSnapshot:
    holding_count: int
    tickers: tuple[str, ...]
    library_count: int


def is_chatbot_enabled() -> bool:
    """Feature flag (default on). Set DIVIDENDSCOPE_CHATBOT_ENABLED=0 to hide UI."""
    flag = os.environ.get("DIVIDENDSCOPE_CHATBOT_ENABLED", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def huggingface_configured() -> bool:
    return bool(_huggingface_token())


def _huggingface_token() -> str:
    return (os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN") or "").strip()


def _huggingface_model() -> str:
    return (os.environ.get("DIVIDENDSCOPE_CHATBOT_MODEL") or HF_MODEL_DEFAULT).strip()


def _session_portfolio_snapshot() -> SessionPortfolioSnapshot | None:
    try:
        import streamlit as st
    except Exception:
        return None

    rows = st.session_state.get("portfolio_details_rows") or []
    tickers = tuple(t for t in (getattr(r, "ticker", "") or "" for r in rows) if t)
    market = st.session_state.get("market_db_status") or {}
    library_count = int(market.get("document_count") or 0)
    if not tickers and not st.session_state.get("portfolio_fast_loaded"):
        return None
    return SessionPortfolioSnapshot(
        holding_count=len(rows),
        tickers=tickers,
        library_count=library_count,
    )


def build_session_context() -> str:
    """One-line session hint (legacy helper)."""
    snap = _session_portfolio_snapshot()
    if snap is None:
        return ""
    parts: list[str] = []
    if snap.holding_count:
        sample = ", ".join(snap.tickers[:10])
        suffix = "…" if len(snap.tickers) > 10 else ""
        parts.append(f"{snap.holding_count} holdings ({sample}{suffix})")
    if snap.library_count > 0:
        parts.append(f"{snap.library_count} analysed tickers in library")
    return "; ".join(parts)


def format_assistant_reply(body: str, *, show_hf_tip: bool = False) -> str:
    """Append disclaimer; optional one-time HF setup hint."""
    parts = [body.strip()]
    if show_hf_tip and not huggingface_configured():
        parts.append(
            "_Optional: set `HUGGINGFACE_API_KEY` on the server for broader chit-chat "
            "beyond app help._"
        )
    parts.append(DISCLAIMER)
    return "\n\n".join(parts)


def match_local_faq(message: str) -> str | None:
    """Return a curated answer when the user asks about app features."""
    text = (message or "").strip().lower()
    if not text:
        return None
    for keywords, answer in _APP_FAQ:
        if any(keyword in text for keyword in keywords):
            return answer
    return None


def match_session_reply(message: str) -> str | None:
    """Answers that use the current portfolio session (no LLM)."""
    text = (message or "").strip()
    lower = text.lower()
    snap = _session_portfolio_snapshot()

    if re.search(r"\b(hello|hi|hey|thanks)\b", lower) or "thank you" in lower:
        if snap and snap.holding_count:
            return (
                f"Hello! You have **{snap.holding_count}** holdings loaded — ask about a ticker "
                f"(e.g. **{snap.tickers[0]}**), **yield channels**, or **dividend sync**."
            )
        return (
            "Hello! Add holdings under **Manage portfolio**, then **Reload live data**. "
            "Ask me about yield channels, dividends, or the shared S&P library."
        )

    if snap and snap.holding_count:
        if any(
            phrase in lower
            for phrase in (
                "my portfolio",
                "my holdings",
                "how many holdings",
                "how many stocks",
                "what do i own",
                "list holdings",
                "show portfolio",
            )
        ):
            sample = ", ".join(snap.tickers[:12])
            more = f" (+{snap.holding_count - 12} more)" if snap.holding_count > 12 else ""
            lib = (
                f" The shared library has **{snap.library_count}** analysed tickers."
                if snap.library_count
                else ""
            )
            return (
                f"Your session has **{snap.holding_count}** holdings: {sample}{more}.{lib} "
                "Use the **Holdings** table to compare positions, **Dividends** for income, "
                "or open a ticker for yield-channel detail."
            )

        mentioned = [t for t in _TICKER_RE.findall(text.upper()) if t in snap.tickers]
        if mentioned:
            symbol = mentioned[0]
            return (
                f"**{symbol}** is in your portfolio. In **Holdings**, filter or open **{symbol}** "
                "for fundamentals, yield channels (vs its own history), and same-sector peers. "
                "If the yield chart is missing, use **Reload live data**."
            )

    # Ticker in library but not held — still helpful
    if snap and snap.library_count:
        tokens = _TICKER_RE.findall(text.upper())
        if tokens and not snap.tickers:
            symbol = next((t for t in tokens if len(t) > 1), tokens[0])
            return (
                f"To analyse **{symbol}**, use S&P research from the app home/examples, "
                "or add it under **Manage portfolio** then **Reload live data**. The library has "
                f"**{snap.library_count}** enriched tickers."
            )

    return None


def _bot_turn_for_history(content: str) -> str:
    """Trim disclaimer/markdown noise before sending prior turns to BlenderBot."""
    text = (content or "").strip()
    if not text or text == WELCOME_MESSAGE:
        return ""
    if DISCLAIMER in text:
        text = text.split(DISCLAIMER, 1)[0].strip()
    return text


def coerce_chat_prompt(raw: object) -> str:
    """Normalize st.chat_input return value (str, dict, or ChatInputValue)."""
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


def _pair_conversation_history(
    messages: Sequence[ChatMessage],
) -> tuple[list[str], list[str]]:
    """Build BlenderBot past_user_inputs / generated_responses from chat history."""
    past_user: list[str] = []
    past_bot: list[str] = []
    seen_user = False
    for msg in messages:
        if msg.role == "user":
            seen_user = True
            past_user.append(msg.content)
        elif msg.role == "assistant":
            if not seen_user:
                continue
            turn = _bot_turn_for_history(msg.content)
            if turn:
                past_bot.append(turn)
    while len(past_bot) < len(past_user) - 1:
        past_bot.insert(0, "")
    while len(past_user) > len(past_bot) + 1:
        past_user.pop(0)
        if past_bot:
            past_bot.pop(0)
    past_user = past_user[:-1][-3:]
    past_bot = past_bot[-3:]
    return past_user, past_bot


def reply_via_huggingface(  # noqa: C901
    user_message: str,
    messages: Sequence[ChatMessage],
    *,
    token: str | None = None,
    model: str | None = None,
    timeout: int = 25,
) -> str | None:
    """Call Hugging Face Inference API from the server."""
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


def fallback_reply(_user_message: str) -> str:
    """Short default when no FAQ/session/LLM match."""
    snap = _session_portfolio_snapshot()
    if snap and snap.holding_count:
        lead = (
            f"I didn't match that to a specific feature. With **{snap.holding_count}** "
            f"holdings loaded, try **{snap.tickers[0]}** (ticker name), **yield channels**, "
            "**Reload live data**, or **Dividends**."
        )
    else:
        lead = (
            "I didn't match that to a specific feature. Try **Manage portfolio**, "
            "**Reload live data**, **yield channels**, or **dividend sync**."
        )
    return lead


def generate_reply(
    user_message: str,
    messages: Sequence[ChatMessage],
    *,
    show_hf_tip_on_fallback: bool = False,
) -> str:
    """
    Produce the assistant reply for a user turn.

    App FAQ and session-aware answers are preferred; optional HF fills general chat.
    """
    text = (user_message or "").strip()
    if not text:
        return "Please enter a message."

    for matcher in (match_local_faq, match_session_reply):
        answer = matcher(text)
        if answer:
            return format_assistant_reply(answer)

    llm_reply = reply_via_huggingface(text, messages)
    if llm_reply:
        return format_assistant_reply(llm_reply)

    return format_assistant_reply(
        fallback_reply(text),
        show_hf_tip=show_hf_tip_on_fallback,
    )


def initial_messages() -> list[dict[str, str]]:
    """Default chat history for st.session_state."""
    return [{"role": "assistant", "content": WELCOME_MESSAGE}]
