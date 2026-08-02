"""
Dividend transaction classification and stable deduplication keys.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

TRANSACTION_STATUS_POSTED = "posted"
TRANSACTION_STATUS_CANCELLED = "cancelled"
TRANSACTION_STATUS_FORECAST = "forecast"

DIVIDEND_TYPE_ACTUAL = "actual"
DIVIDEND_TYPE_PAYMENT_IN_LIEU = "payment_in_lieu"
DIVIDEND_TYPE_COMPUTED = "computed"
DIVIDEND_TYPE_ACCRUAL = "accrual"
DIVIDEND_TYPE_WITHHOLDING = "withholding"
DIVIDEND_TYPE_REVERSAL = "reversal"
DIVIDEND_TYPE_FORECAST = "forecast"

POSTED_CASH_DIVIDEND_TYPES = frozenset({DIVIDEND_TYPE_ACTUAL, DIVIDEND_TYPE_PAYMENT_IN_LIEU})


@dataclass(frozen=True)
class DividendDedupInput:
    broker_account: str | None
    broker_transaction_id: str | None
    symbol: str
    isin: str | None
    pay_date: date
    currency: str
    gross_usd: float
    withholding_usd: float
    net_usd: float


def build_dedup_key(payload: DividendDedupInput) -> str:
    """
    Stable idempotency key for broker dividend rows.

    Prefer broker transaction id when present; otherwise hash economic fields
    (filename is intentionally excluded so overlapping exports dedupe).
    """
    account = (payload.broker_account or "").strip()
    tx_id = (payload.broker_transaction_id or "").strip()
    if account and tx_id:
        return f"{account}:{tx_id}"

    canonical = "|".join(
        [
            account,
            payload.symbol.strip().upper(),
            (payload.isin or "").strip().upper(),
            payload.pay_date.isoformat(),
            payload.currency.strip().upper(),
            f"{payload.gross_usd:.2f}",
            f"{payload.withholding_usd:.2f}",
            f"{payload.net_usd:.2f}",
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def net_from_gross_and_withholding(*, gross_usd: float, withholding_usd: float) -> float:
    """``net = gross - withholding`` (withholding stored as a positive amount)."""
    return round(max(gross_usd - max(withholding_usd, 0.0), 0.0), 2)


def extract_isin(description: str) -> str | None:
    """Pull ISIN from IBKR dividend description parentheses."""
    start = description.find("(")
    end = description.find(")", start + 1)
    if start < 0 or end <= start + 1:
        return None
    token = description[start + 1 : end].strip().upper()
    if len(token) >= 10 and token[:2].isalpha():
        return token
    return None
