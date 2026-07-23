"""Decimal helpers for broker import normalization."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CURRENCY = Decimal("0.01")
_SHARES = Decimal("0.0001")
_RATE = Decimal("0.000001")


def _quantize(value: Decimal, step: Decimal) -> float:
    return float(value.quantize(step, rounding=ROUND_HALF_UP))


def round_money(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        return _quantize(Decimal(str(value)), _CURRENCY)
    except (InvalidOperation, ValueError):
        return 0.0


def round_shares(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        return _quantize(Decimal(str(value)), _SHARES)
    except (InvalidOperation, ValueError):
        return 0.0


def round_rate(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        return _quantize(Decimal(str(value)), _RATE)
    except (InvalidOperation, ValueError):
        return 0.0
