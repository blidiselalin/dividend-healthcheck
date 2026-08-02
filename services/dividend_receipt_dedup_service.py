"""
Backfill dedup keys and reconcile duplicate dividend receipt rows.
"""

from __future__ import annotations

from typing import Any


def reconcile_dividend_receipts(receipt_store: Any) -> tuple[int, int]:
    """
    Backfill missing dedup keys and mark duplicate rows excluded.

    Returns ``(keys_backfilled, duplicates_marked)``.
    """
    backfilled = receipt_store.backfill_dedup_keys()
    marked = receipt_store.dedupe_mark_duplicates()
    return backfilled, marked
