"""Styled dividend timing tables."""
# ruff: noqa: S101

from __future__ import annotations

import pandas as pd

from services.dividend_timing import (
    PAID,
    TIMING_LABELS,
    UPCOMING_EX,
    classify_dividend_timing,
    style_dividend_timing_dataframe,
)


def test_style_preserves_row_count() -> None:
    df = pd.DataFrame(
        [
            {"Ticker": "KO", "Timing": TIMING_LABELS[UPCOMING_EX]},
            {"Ticker": "VZ", "Timing": TIMING_LABELS[PAID]},
        ]
    )
    styled = style_dividend_timing_dataframe(df)
    assert len(styled.data) == 2


def test_classify_ex_passed_pay_upcoming() -> None:
    label = classify_dividend_timing(
        today=__import__("datetime").date(2026, 5, 15),
        ex_date=__import__("datetime").date(2026, 5, 10),
        pay_date=__import__("datetime").date(2026, 5, 28),
    )
    assert "passed" in label.lower()
