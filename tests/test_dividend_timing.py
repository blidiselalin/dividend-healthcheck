"""Dividend timing labels (upcoming vs paid)."""

from __future__ import annotations

from datetime import date

from services.dividend_timing import TIMING_LABELS, UPCOMING_EX, classify_dividend_timing


def test_upcoming_ex_date() -> None:
    today = date(2026, 5, 10)
    label = classify_dividend_timing(
        today=today,
        ex_date=date(2026, 5, 20),
        pay_date=date(2026, 6, 5),
    )
    assert label == TIMING_LABELS[UPCOMING_EX]


def test_ex_passed_payment_upcoming() -> None:
    today = date(2026, 5, 15)
    label = classify_dividend_timing(
        today=today,
        ex_date=date(2026, 5, 10),
        pay_date=date(2026, 5, 25),
    )
    assert "passed" in label.lower()


def test_paid_when_pay_date_in_past() -> None:
    today = date(2026, 5, 20)
    label = classify_dividend_timing(
        today=today,
        ex_date=date(2026, 4, 1),
        pay_date=date(2026, 5, 1),
    )
    assert label == "Paid"
