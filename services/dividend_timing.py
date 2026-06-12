"""
Classify dividend rows as upcoming vs paid (informational — not risk severity).
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Internal keys
UPCOMING_EX = "upcoming_ex"
EX_PASSED_PAY_UPCOMING = "ex_passed_pay_upcoming"
UPCOMING_PAY = "upcoming_pay"
PAID = "paid"
PROJECTED = "projected"
SCHEDULED = "scheduled"

TIMING_LABELS = {
    UPCOMING_EX: "Upcoming ex-date",
    EX_PASSED_PAY_UPCOMING: "Ex-date passed · payment upcoming",
    UPCOMING_PAY: "Upcoming payment",
    PAID: "Paid",
    PROJECTED: "Projected (estimated)",
    SCHEDULED: "Scheduled",
}

# Background, text (for pandas Styler)
TIMING_ROW_COLORS: dict[str, tuple[str, str]] = {
    UPCOMING_EX: ("#e3f2fd", "#0d47a1"),
    EX_PASSED_PAY_UPCOMING: ("#fff8e1", "#e65100"),
    UPCOMING_PAY: ("#e8f5e9", "#1b5e20"),
    PAID: ("#f5f5f5", "#616161"),
    PROJECTED: ("#f3e5f5", "#4a148c"),
    SCHEDULED: ("#eceff1", "#37474f"),
}


def classify_dividend_timing(
    *,
    today: date,
    ex_date: date | None = None,
    pay_date: date | None = None,
    status: str | None = None,
) -> str:
    """
    Return a display label for ex-date / payment timing (not a risk severity).
    """
    status_key = (status or "").lower()

    if pay_date is not None and pay_date <= today:
        return TIMING_LABELS[PAID]
    if status_key == "received":
        return TIMING_LABELS[PAID]

    if ex_date is not None and ex_date > today:
        return TIMING_LABELS[UPCOMING_EX]

    if pay_date is not None and pay_date > today:
        if ex_date is not None and ex_date <= today:
            return TIMING_LABELS[EX_PASSED_PAY_UPCOMING]
        return TIMING_LABELS[UPCOMING_PAY]

    if status_key == "projected":
        return TIMING_LABELS[PROJECTED]
    if status_key in ("scheduled", ""):
        if ex_date is not None and ex_date <= today:
            return TIMING_LABELS[EX_PASSED_PAY_UPCOMING]
        return TIMING_LABELS[SCHEDULED]

    return TIMING_LABELS[SCHEDULED]


def label_to_style_key(label: str) -> str:
    for key, text in TIMING_LABELS.items():
        if text == label:
            return key
    return SCHEDULED


def style_dividend_timing_dataframe(df: Any, *, timing_column: str = "Timing") -> Any:
    """Highlight rows by dividend timing (Streamlit-compatible pandas Styler)."""

    if df is None or df.empty or timing_column not in df.columns:
        return df

    def _row_style(row: Any) -> Any:
        label = str(row.get(timing_column, ""))
        key = label_to_style_key(label)
        bg, fg = TIMING_ROW_COLORS.get(key, TIMING_ROW_COLORS[SCHEDULED])
        return [f"background-color: {bg}; color: {fg}"] * len(row)

    return df.style.apply(_row_style, axis=1)
