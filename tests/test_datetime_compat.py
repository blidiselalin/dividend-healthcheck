"""Tests for naive/aware datetime normalization."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import datetime, timezone

from data_ingestion.models import DataSource, StockDocument
from data_ingestion.providers.snapshot import StockSnapshot, apply_snapshot_to_document
from utils.datetime_compat import max_datetime, to_naive_utc


def test_to_naive_utc_strips_timezone() -> None:
    aware = datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc)
    assert to_naive_utc(aware) == datetime(2026, 6, 9, 10, 0)
    assert to_naive_utc(aware).tzinfo is None  # type: ignore[union-attr]


def test_max_datetime_mixed_naive_and_aware() -> None:
    naive = datetime(2026, 6, 8, 12, 0)
    aware = datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc)
    assert max_datetime(naive, aware) == datetime(2026, 6, 9, 10, 0)


def test_apply_snapshot_handles_aware_last_updated() -> None:
    doc = StockDocument(symbol="ABBV", name="AbbVie", source=DataSource.MANUAL)
    doc.last_updated = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    snapshot = StockSnapshot(
        symbol="ABBV",
        source=DataSource.YAHOO,
        fetched_at=datetime(2026, 6, 9, 9, 0),
        current_price=180.0,
    )

    updated = apply_snapshot_to_document(doc, snapshot)

    assert updated.last_updated == datetime(2026, 6, 9, 9, 0)
    assert updated.last_updated.tzinfo is None
