"""
Dividend-growth research screen.

Ranks a shortlist from the shared market library. The model may interpret
and score. It may not invent missing financial fields, and it does not
write portfolio holdings.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from db.parsing import parse_optional_date

logger = logging.getLogger(__name__)

SCREEN_COLUMNS: tuple[str, ...] = (
    "week_start",
    "week_end",
    "rank",
    "ticker",
    "company_name",
    "exchange",
    "sector",
    "industry",
    "currency",
    "market_cap_usd",
    "price_usd",
    "dividend_yield_pct",
    "annual_dividend_per_share_usd",
    "payout_ratio_pct",
    "fcf_payout_ratio_pct",
    "dividend_growth_years",
    "dividend_cagr_5y_pct",
    "revenue_growth_5y_cagr_pct",
    "eps_growth_5y_cagr_pct",
    "fcf_growth_5y_cagr_pct",
    "price_cagr_5y_pct",
    "total_return_5y_pct",
    "forward_eps_growth_pct",
    "pe_ttm",
    "pe_forward",
    "peg_ratio",
    "price_to_fcf",
    "ev_to_ebitda",
    "roe_pct",
    "net_debt_to_ebitda",
    "debt_to_equity",
    "price_change_1y_pct",
    "relative_strength_vs_sp500_1y_pct",
    "distance_from_52w_high_pct",
    "portfolio_phase",
    "drip_suitability",
    "historical_growth_view",
    "valuation_view",
    "dividend_safety_view",
    "next_period_upside_view",
    "historical_growth_score",
    "dividend_quality_score",
    "business_growth_outlook_score",
    "valuation_score",
    "next_period_upside_score",
    "financial_strength_score",
    "sector_diversification_score",
    "total_score",
    "decision_label",
    "decision_reason",
    "key_risks",
    "primary_source",
    "secondary_source",
    "source_confidence",
    "data_as_of",
)

_MIN_MARKET_CAP = 2_000_000_000
_PROMPT_PATH = Path(__file__).with_name("research_screen_prompt.txt")
_SCORE_LIMITS = {
    "historical_growth_score": 15,
    "dividend_quality_score": 20,
    "business_growth_outlook_score": 15,
    "valuation_score": 25,
    "next_period_upside_score": 10,
    "financial_strength_score": 10,
    "sector_diversification_score": 5,
}
_LABELS = {
    "valuation_view": {
        "Exceptional Value",
        "Attractive",
        "Fair Value",
        "Slightly Expensive",
        "Expensive",
    },
    "decision_label": {
        "Strong candidate",
        "Good candidate",
        "Watchlist only",
        "Opportunistic buy only",
        "Avoid for now",
    },
    "portfolio_phase": {
        "Phase 1 - Stability/Income",
        "Phase 2 - Dividend Growth/Capital Gains",
        "Opportunistic Dip Buy",
    },
    "drip_suitability": {"Strong", "Moderate", "Weak"},
}
ASSESSMENT_COLUMNS = (
    "ticker",
    *SCREEN_COLUMNS[34:47],
    "decision_label",
    "decision_reason",
    "key_risks",
)


def screen_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def select_screen_candidates(
    documents: list[Any], *, limit: int = 40, held_symbols: set[str] | None = None
) -> list[Any]:
    """US-listed common stocks above $2B. Highest stored dividend CAGR first."""
    kept: dict[str, Any] = {}
    for document in documents:
        name = str(getattr(document, "name", "") or "").lower()
        if any(word in name for word in ("etf", "fund", "preferred", "acquisition corp", "spac")):
            continue
        symbol = str(getattr(document, "symbol", "") or "").upper()
        exchange = str(getattr(document, "exchange", "") or "").upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", symbol):
            continue
        if exchange not in {"NYSE", "NASDAQ", "NYQ", "NMS", "NGM", "NCM", "ASE", "AMEX"}:
            continue
        cap = _num(getattr(document, "market_cap", None))
        price = _num(getattr(document, "current_price", None))
        dividend = _dividend_yield(document)
        if cap is None or cap < _MIN_MARKET_CAP or price is None or price < 5:
            continue
        if dividend is None or dividend <= 0 or getattr(document, "currency", "USD") != "USD":
            continue
        try:
            snapshot = parse_optional_date(getattr(document, "last_updated", None))
        except (ValueError, TypeError):
            continue
        if snapshot is None or not 0 <= (date.today() - snapshot).days <= 7:
            continue
        kept[symbol] = document
    ordered = sorted(
        kept.values(),
        key=lambda item: (
            str(item.symbol).upper() not in (held_symbols or set()),
            -(_num(getattr(item, "dividend_cagr_5y", None)) or 0),
            -(_num(getattr(item, "dividend_streak_years", None)) or 0),
            str(item.symbol).upper(),
        ),
    )
    return ordered[
        : max(limit, sum(str(item.symbol).upper() in (held_symbols or set()) for item in ordered))
    ]


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _dividend_yield(document: Any) -> float | None:
    stored = _num(getattr(document, "dividend_yield", None))
    if stored is not None and stored <= 0:
        return stored
    annual = _num(getattr(document, "annual_dividend", None))
    price = _num(getattr(document, "current_price", None))
    if annual is not None and annual >= 0 and price is not None and price > 0:
        return round(annual / price * 100, 4)
    return stored


def candidate_packet(document: Any, *, as_of: date | None = None) -> dict[str, Any]:
    """Stored library fields only. Missing metrics stay absent."""
    high = _num(getattr(document, "fifty_two_week_high", None))
    price = _num(getattr(document, "current_price", None))
    screen_date = as_of or date.today()
    snapshot_date = parse_optional_date(getattr(document, "last_updated", None))
    if snapshot_date and snapshot_date > screen_date:
        raise ValueError(f"{document.symbol}: snapshot was not available on the requested date.")
    price_return = _num(getattr(document, "price_return_5y", None))
    price_cagr = None
    if price_return is not None and price_return > -100:
        price_cagr = round(((1 + price_return / 100) ** (1 / 5) - 1) * 100, 4)
    distance = None
    if high and price and float(high) > 0:
        distance = round((float(price) / float(high) - 1) * 100, 2)
    packet = {
        "ticker": getattr(document, "symbol", None),
        "company_name": getattr(document, "name", None),
        "exchange": getattr(document, "exchange", None),
        "sector": getattr(document, "sector", None),
        "industry": getattr(document, "industry", None),
        "currency": "USD",
        "market_cap_usd": _num(getattr(document, "market_cap", None)),
        "price_usd": _num(price),
        "dividend_yield_pct": _dividend_yield(document),
        "annual_dividend_per_share_usd": _num(getattr(document, "annual_dividend", None)),
        "payout_ratio_pct": _num(getattr(document, "payout_ratio", None)),
        "fcf_payout_ratio_pct": _num(getattr(document, "fcf_payout_ratio", None)),
        "dividend_growth_years": _num(getattr(document, "dividend_streak_years", None)),
        "dividend_cagr_5y_pct": _num(getattr(document, "dividend_cagr_5y", None)),
        "revenue_growth_yoy_pct": _num(getattr(document, "revenue_growth", None)),
        "eps_growth_yoy_pct": _num(getattr(document, "earnings_growth", None)),
        "fcf_growth_yoy_pct": _num(getattr(document, "fcf_growth", None)),
        "price_cagr_5y_pct": price_cagr,
        "total_return_5y_pct": _num(getattr(document, "total_return_5y", None)),
        "pe_ttm": _num(getattr(document, "pe_ratio", None)),
        "pe_forward": _num(getattr(document, "forward_pe", None)),
        "peg_ratio": _num(getattr(document, "peg_ratio", None)),
        "ev_to_ebitda": _num(getattr(document, "ev_ebitda", None)),
        "roe_pct": _num(getattr(document, "roe", None)),
        "debt_to_equity": _num(getattr(document, "debt_to_equity", None)),
        "debt_to_ebitda": _num(getattr(document, "debt_to_ebitda", None)),
        "price_change_1y_pct": _num(getattr(document, "price_return_1y", None)),
        "distance_from_52w_high_pct": distance,
        "data_as_of": snapshot_date.isoformat() if snapshot_date else "",
        "confidence_limit": "Medium"
        if snapshot_date and (screen_date - snapshot_date).days <= 7
        else "Low",
        "secondary_source": "Stored market library: "
        + str(getattr(getattr(document, "source", None), "value", "unknown")),
        "evidence_limitations": (
            "Snapshot update date; quote timestamp and financial reporting periods are unverified. "
            "Primary filing citations are unavailable."
        ),
        "source": str(getattr(getattr(document, "source", None), "value", None) or "library"),
        "business_description": str(getattr(document, "description", "") or "")[:1500],
    }
    sector = str(packet["sector"] or "").lower()
    industry = str(packet["industry"] or "").lower()
    if "bank" in industry or "insurance" in industry:
        for field in (
            "fcf_payout_ratio_pct",
            "ev_to_ebitda",
            "debt_to_ebitda",
            "debt_to_equity",
        ):
            packet.pop(field, None)
    if "reit" in industry or "real estate" in sector:
        packet.pop("fcf_payout_ratio_pct", None)
    stored_yield = _num(getattr(document, "dividend_yield", None))
    calculated_yield = _num(packet["dividend_yield_pct"])
    if (
        stored_yield is not None
        and calculated_yield is not None
        and abs(stored_yield - calculated_yield) > 1
    ):
        packet["data_warnings"] = (
            "Stored yield conflicts with annual dividend/price; calculated yield used."
        )
    return {key: value for key, value in packet.items() if value is not None}


def screen_user_message(candidates: list[Any], *, as_of: date | None = None) -> str:
    if len(candidates) != 1:
        raise ValueError("Each model request must review exactly one ticker.")
    packet = candidate_packet(candidates[0], as_of=as_of)
    packet["business_description"] = packet.get("business_description", "")[:600]
    for field in ("source", "secondary_source", "evidence_limitations", "currency"):
        packet.pop(field, None)
    return (
        "Assess this ticker using only authoritative INPUT_DATA. Return JSON rows with "
        "at most one assessment; use an empty array if evidence is insufficient.\nINPUT_DATA:\n"
        + json.dumps(packet, separators=(",", ":"), default=str)
    )


@dataclass(frozen=True)
class LlmTarget:
    url: str
    model: str
    api_key: str
    kind: str


def _chat_url(url: str) -> str:
    cleaned = url.rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    return cleaned + "/chat/completions"


def resolve_llm_target() -> LlmTarget | None:
    """Local OpenAI-compatible endpoint first, then a configured cloud endpoint."""
    local = os.environ.get("DIVIDENDSCOPE_LOCAL_LLM_URL", "").strip()
    if local:
        return LlmTarget(
            url=_chat_url(local),
            model=os.environ.get("DIVIDENDSCOPE_LOCAL_LLM_MODEL", "llama3.1").strip(),
            api_key=os.environ.get("DIVIDENDSCOPE_LOCAL_LLM_API_KEY", "").strip(),
            kind="local",
        )
    cloud = os.environ.get("DIVIDENDSCOPE_LLM_API_URL", "").strip()
    cloud_key = (
        os.environ.get("DIVIDENDSCOPE_LLM_API_KEY")
        or os.environ.get("HUGGINGFACE_API_KEY")
        or os.environ.get("HF_TOKEN")
        or ""
    ).strip()
    if cloud and cloud_key:
        model = os.environ.get("DIVIDENDSCOPE_LLM_MODEL") or os.environ.get(
            "DIVIDENDSCOPE_CHATBOT_MODEL", ""
        )
        return LlmTarget(url=_chat_url(cloud), model=model.strip(), api_key=cloud_key, kind="cloud")
    if cloud_key and not cloud:
        model = (
            os.environ.get("DIVIDENDSCOPE_LLM_MODEL")
            or os.environ.get("DIVIDENDSCOPE_CHATBOT_MODEL")
            or "meta-llama/Llama-3.1-8B-Instruct"
        )
        return LlmTarget(
            url="https://router.huggingface.co/v1/chat/completions",
            model=model.strip(),
            api_key=cloud_key,
            kind="cloud",
        )
    return None


def parse_screen_csv(text: str) -> list[dict[str, str]]:
    """Parse the model CSV. Raises ValueError when the header is not the schema."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    reader = csv.DictReader(io.StringIO(cleaned))
    header = tuple(reader.fieldnames or ())
    if header != SCREEN_COLUMNS:
        raise ValueError("Screen CSV header does not match the 55-column schema")
    rows = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Every CSV row must contain exactly 55 fields.")
        if not any((value or "").strip() for value in row.values()):
            continue
        rows.append({column: (row.get(column) or "").strip() for column in SCREEN_COLUMNS})
    symbols = [row["ticker"].upper() for row in rows]
    if len(rows) > 10 or len(symbols) != len(set(symbols)) or any(not symbol for symbol in symbols):
        raise ValueError("Return at most 10 unique supplied tickers.")
    return rows


def validate_screen_rows(
    rows: list[dict[str, str]], candidates: list[Any], *, as_of: date | None = None
) -> None:
    """Reject invented metrics/tickers, inconsistent scores and unsupported confidence."""
    screen_date = as_of or date.today()
    packets = {
        str(doc.symbol).upper(): candidate_packet(doc, as_of=screen_date) for doc in candidates
    }
    for rank, row in enumerate(rows, 1):
        packet = packets.get(row["ticker"].upper())
        if packet is None or _num(row["rank"]) != rank:
            raise ValueError("Screen ranks or tickers do not match the supplied universe.")
        _validate_evidence(row, packet, screen_date)
        scores = [_num(row[key]) for key in _SCORE_LIMITS]
        if any(
            value is None or not 0 <= value <= maximum
            for value, maximum in zip(scores, _SCORE_LIMITS.values(), strict=True)
        ):
            raise ValueError("Screen component scores are missing or outside their limits.")
        total = _num(row["total_score"])
        if total is None or not math.isclose(
            math.fsum(value for value in scores if value is not None), total, abs_tol=0.01
        ):
            raise ValueError("Total score does not equal the seven component scores.")
        if any(row[key] not in labels for key, labels in _LABELS.items()):
            raise ValueError(
                "The screen returned an unsupported decision, valuation or role label."
            )
        if not row["decision_reason"] or not row["key_risks"]:
            raise ValueError("Each ranked stock needs a decision reason and key risks.")
        if row["source_confidence"] != "Medium" or packet["confidence_limit"] == "Low":
            raise ValueError(
                "The screen's source confidence is unsupported by the stored evidence."
            )


def _validate_evidence(row: dict[str, str], packet: dict[str, Any], screen_date: date) -> None:
    for field in SCREEN_COLUMNS[9:34]:
        raw = row[field]
        if not raw and field not in {"market_cap_usd", "price_usd"}:
            continue
        value, supplied = _num(raw), _num(packet.get(field))
        if (
            value is None
            or supplied is None
            or not math.isclose(value, supplied, rel_tol=1e-6, abs_tol=0.01)
        ):
            raise ValueError(f"{row['ticker']}: {field} is absent from or differs from INPUT_DATA.")
    for field in (
        "company_name",
        "exchange",
        "sector",
        "industry",
        "currency",
        "data_as_of",
        "secondary_source",
    ):
        if row[field] != str(packet.get(field) or ""):
            raise ValueError(f"{row['ticker']}: {field} must match the stored evidence.")
    start = screen_date - timedelta(days=screen_date.weekday())
    if row["week_start"] != start.isoformat() or row["week_end"] != screen_date.isoformat():
        raise ValueError("Screen dates must match this run's point-in-time context.")
    if row["primary_source"]:
        raise ValueError("Primary filing citations are unavailable in this input snapshot.")


def _message_text(payload: Any) -> str:
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
        generated = payload.get("generated_text")
        if isinstance(generated, str):
            return generated
    return ""


def request_screen_csv(
    candidates: list[Any],
    *,
    target: LlmTarget,
    timeout: int = 60,
    as_of: date | None = None,
) -> str:
    """Assess one ticker; assemble financial fields and CSV in deterministic code."""
    import requests

    screen_date = as_of or date.today()
    user_message = screen_user_message(candidates, as_of=screen_date)
    packet = candidate_packet(candidates[0], as_of=screen_date)
    if packet["confidence_limit"] != "Medium":
        raise ValueError("A recent dated snapshot is required before reviewing this ticker.")
    properties: dict[str, Any] = {
        column: {"type": "string", "maxLength": 300} for column in ASSESSMENT_COLUMNS
    }
    for column, labels in _LABELS.items():
        properties[column]["enum"] = sorted(labels)
    properties["ticker"]["enum"] = [packet["ticker"]]
    properties["sector_diversification_score"]["enum"] = ["0"]
    body = {
        "model": target.model,
        "temperature": 0.1,
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": screen_prompt()},
            {"role": "user", "content": user_message},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "single_stock_review",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "rows": {
                            "type": "array",
                            "maxItems": 1,
                            "items": {
                                "type": "object",
                                "properties": properties,
                                "required": list(ASSESSMENT_COLUMNS),
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["rows"],
                    "additionalProperties": False,
                },
            },
        },
    }
    if target.url == "https://openrouter.ai/api/v1/chat/completions":
        body["reasoning"] = {"enabled": False, "exclude": True}
        body["provider"] = {"require_parameters": True}
    headers = {"Content-Type": "application/json"}
    if target.api_key:
        headers["Authorization"] = f"Bearer {target.api_key}"
    response = requests.post(target.url, headers=headers, json=body, timeout=timeout)
    response.raise_for_status()
    payload = json.loads(_message_text(response.json()))
    if not isinstance(payload, dict) or set(payload) != {"rows"}:
        raise ValueError("The model must return a rows object for one ticker.")
    assessments = payload["rows"]
    if (
        not isinstance(assessments, list)
        or len(assessments) > 1
        or any(
            not isinstance(row, dict)
            or set(row) != set(ASSESSMENT_COLUMNS)
            or any(not isinstance(value, str) or len(value) > 300 for value in row.values())
            for row in assessments
        )
    ):
        raise ValueError("Return at most one row with exactly the assessment string fields.")
    rows = []
    for assessment in assessments:
        if assessment["ticker"] != packet["ticker"]:
            raise ValueError("The returned ticker differs from the requested ticker.")
        if assessment["sector_diversification_score"] != "0":
            raise ValueError("Portfolio diversification cannot be assessed from one stock.")
        row = {column: str(packet.get(column, "")) for column in SCREEN_COLUMNS}
        row.update(assessment)
        row.update(
            rank="1",
            week_start=(screen_date - timedelta(days=screen_date.weekday())).isoformat(),
            week_end=screen_date.isoformat(),
            source_confidence=packet["confidence_limit"],
            total_score=format(
                math.fsum(_num(assessment[key]) or 0 for key in _SCORE_LIMITS), ".10g"
            ),
        )
        rows.append(row)
    validate_screen_rows(rows, candidates, as_of=screen_date)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=SCREEN_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def run_screen(
    candidates: list[Any],
    *,
    target: LlmTarget,
    timeout: int = 60,
    as_of: date | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Review unique tickers sequentially and combine validated scores without another LLM call."""
    import requests

    unique: dict[str, Any] = {}
    for document in candidates:
        unique.setdefault(str(document.symbol).strip().upper(), document)
    documents = list(unique.values())
    rows: list[dict[str, str]] = []
    failures: dict[str, str] = {}
    screen_date = as_of or date.today()
    for index, document in enumerate(documents):
        symbol = str(document.symbol).upper()
        if on_progress:
            on_progress(index, len(documents), symbol)
        stop = False
        try:
            result = request_screen_csv(
                [document], target=target, timeout=timeout, as_of=screen_date
            )
            ticker_rows = parse_screen_csv(result)
            validate_screen_rows(ticker_rows, [document], as_of=screen_date)
            rows.extend(ticker_rows)
        except (ValueError, requests.RequestException) as error:
            status = (
                error.response.status_code
                if isinstance(error, requests.HTTPError) and error.response is not None
                else None
            )
            if status in {401, 403}:
                reason = "Model authentication failed"
            elif status == 429:
                reason = "Provider rate limit reached"
            elif isinstance(error, ValueError):
                reason = "Invalid model response"
            else:
                reason = "Model request failed"
            failures[symbol] = reason
            logger.warning("Ticker review failed: %s (%s)", symbol, type(error).__name__)
            stop = status in {401, 403, 429}
            if stop:
                for remaining in documents[index + 1 :]:
                    failures[str(remaining.symbol).upper()] = "Not reviewed: " + reason
        if on_progress:
            on_progress(index + 1, len(documents), symbol)
        if stop:
            break
    rows.sort(key=lambda row: (-float(row["total_score"]), row["ticker"]))
    rows = rows[:10]
    for rank, row in enumerate(rows, 1):
        row["rank"] = str(rank)
    validate_screen_rows(rows, documents, as_of=screen_date)
    return rows, failures
