"""Accessible definitions for dividend metrics shown in the UI."""

from __future__ import annotations

from collections.abc import Mapping

DIVIDEND_TERMS: Mapping[str, str] = {
    "gross_dividend": "The dividend amount before taxes and deductions.",
    "withholding_tax": "Tax deducted by the broker or payment source.",
    "net_dividend": "The amount received after withholding tax and other deductions.",
    "received_dividend": "A completed cash transaction reported by the broker.",
    "accrued_dividend": "A dividend recorded by the broker but not yet paid.",
    "estimated_dividend": (
        "A projected amount based on current holdings and available dividend information."
    ),
    "payment_date": "The date the broker expects cash to be paid to holders.",
    "ex_dividend_date": (
        "The first trading day when a share no longer carries the upcoming dividend."
    ),
    "dividend_yield": "Annual dividend income as a percentage of the current share price.",
    "yield_on_cost": ("Expected annual dividend income divided by the original investment cost."),
    "annual_dividend_income": (
        "Estimated dividends from current holdings over the next twelve months."
    ),
}

# Display labels used by tooltips / help popovers.
DIVIDEND_TERM_LABELS: Mapping[str, str] = {
    "gross_dividend": "Gross dividend",
    "withholding_tax": "Withholding tax",
    "net_dividend": "Net dividend",
    "received_dividend": "Received dividend",
    "accrued_dividend": "Accrued dividend",
    "estimated_dividend": "Estimated dividend",
    "payment_date": "Payment date",
    "ex_dividend_date": "Ex-dividend date",
    "dividend_yield": "Dividend yield",
    "yield_on_cost": "Yield on cost",
    "annual_dividend_income": "Annual dividend income",
}


def term_help(term_id: str) -> str:
    """Return the definition for a term id, or empty string if unknown."""
    return str(DIVIDEND_TERMS.get(term_id, ""))


def term_label(term_id: str) -> str:
    return str(DIVIDEND_TERM_LABELS.get(term_id, term_id.replace("_", " ").title()))
