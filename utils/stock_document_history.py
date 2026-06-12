"""
Shared helpers for price/dividend history on ``StockDocument`` records.

History is stored in PostgreSQL ``stock_documents.document`` JSONB as
``price_history`` and ``dividend_history`` arrays. Legacy Chroma exports
sometimes only persisted ``price_history_json`` / ``dividend_history_json``.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from config import MIN_YIELD_DIVIDEND_PAYMENTS, MIN_YIELD_PRICE_POINTS

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from data_ingestion.models import StockDocument


def history_counts(doc: Any) -> tuple[int, int]:
    prices = getattr(doc, "price_history", None) or []
    dividends = getattr(doc, "dividend_history", None) or []
    return len(prices), len(dividends)


def history_is_thin(doc: Any) -> bool:
    """True when yield channels and history tables need a backfill."""
    from utils.yfinance_history import library_prices_trustworthy, unique_price_dates

    price_n, div_n = history_counts(doc)
    unique_prices = unique_price_dates(doc)
    prices_thin = not library_prices_trustworthy(doc, min_unique=MIN_YIELD_PRICE_POINTS)
    if price_n >= MIN_YIELD_PRICE_POINTS and unique_prices < max(52, price_n // 4):
        prices_thin = True
    return prices_thin or div_n < MIN_YIELD_DIVIDEND_PAYMENTS


def yield_channel_ready(doc: Any) -> bool:
    from utils.yfinance_history import library_prices_trustworthy

    _, div_n = history_counts(doc)
    return (
        library_prices_trustworthy(doc, min_unique=MIN_YIELD_PRICE_POINTS)
        and div_n >= MIN_YIELD_DIVIDEND_PAYMENTS
    )


def parse_history_payload(data: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    """
    Extract price/dividend history lists from a document dict.

    Supports modern ``price_history`` arrays and legacy ``*_json`` string fields.
    """
    price_raw = data.get("price_history")
    if not price_raw and data.get("price_history_json"):
        price_raw = _loads_json_field(data.get("price_history_json"))
    if not isinstance(price_raw, list):
        price_raw = []

    div_raw = data.get("dividend_history")
    if not div_raw and data.get("dividend_history_json"):
        div_raw = _loads_json_field(data.get("dividend_history_json"))
    if not isinstance(div_raw, list):
        div_raw = []

    return price_raw, div_raw


def hydrate_document_history(doc: StockDocument) -> StockDocument:  # noqa: C901
    """Fill in-memory history from legacy JSON string metadata when arrays are empty."""
    from data_ingestion.models import DividendRecord, PriceHistory

    if not doc.price_history:
        payload = getattr(doc, "price_history_json", None)
        if payload:
            for item in _loads_json_field(payload):
                try:
                    doc.price_history.append(PriceHistory.from_dict(item))
                except Exception as exc:
                    logger.debug("Failed to hydrate price history: %s", exc)
                    continue

    if not doc.dividend_history:
        payload = getattr(doc, "dividend_history_json", None)
        if payload:
            for item in _loads_json_field(payload):
                try:
                    doc.dividend_history.append(DividendRecord.from_dict(item))
                except Exception as exc:
                    logger.debug("Failed to hydrate dividend history: %s", exc)
                    continue

    if doc.price_history:
        doc.price_history.sort(key=lambda point: point.date, reverse=True)
    if doc.dividend_history:
        doc.dividend_history.sort(key=lambda record: record.ex_date, reverse=True)
    return doc


def _loads_json_field(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []
