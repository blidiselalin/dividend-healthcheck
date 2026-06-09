"""Tests for JSON NaN sanitization."""

from __future__ import annotations

import json
import math

from utils.json_safe import finite_float, sanitize_for_json


def test_finite_float_rejects_nan():
    assert finite_float(float("nan")) is None
    assert finite_float(1.5) == 1.5


def test_sanitize_for_json_replaces_nan_recursively():
    payload = {
        "price_history": [
            {"date": "2016-06-08", "open": math.nan, "close": 10.0},
        ],
        "dividend_yield": math.inf,
    }
    cleaned = sanitize_for_json(payload)
    encoded = json.dumps(cleaned)
    assert "NaN" not in encoded
    assert cleaned["price_history"][0]["open"] is None
    assert cleaned["dividend_yield"] is None


def test_postgres_store_payload_is_json_safe():
    from datetime import date

    from data_ingestion.models import PriceHistory, StockDocument

    doc = StockDocument(symbol="TST", name="Test")
    doc.price_history = [
        PriceHistory(
            date=date(2016, 6, 8),
            open=float("nan"),
            high=11.0,
            low=9.0,
            close=10.0,
            volume=100,
        )
    ]
    from utils.json_safe import sanitize_for_json

    blob = json.dumps(sanitize_for_json(doc.to_full_dict()))
    assert "NaN" not in blob
