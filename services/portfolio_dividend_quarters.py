"""
Quarterly dividend cash totals (gross, by payment-date calendar quarter).

Used to validate imported IBKR receipts against broker reference statements.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from data_ingestion.dividend_income_store import MonthlyNetDividend

# IBKR-style annual net dividends (USD) — broker reference for validation.
IBKR_REFERENCE_ANNUAL_NET: dict[int, float] = {
    2022: 3.24,
    2023: 975.09,
    2024: 2021.15,
    2025: 3340.20,
    2026: 2268.52,
}

# Broker report cutoff for partial-year reference totals (must match export date).
IBKR_REFERENCE_THROUGH_DATE = date(2026, 7, 20)

# Quarterly gross reference (legacy spreadsheet export).
IBKR_REFERENCE_QUARTERLY_GROSS: dict[tuple[int, int], float] = {
    (2022, 4): 3.24,
    (2023, 1): 95.62,
    (2023, 2): 214.39,
    (2023, 3): 290.36,
    (2023, 4): 374.72,
    (2024, 1): 410.28,
    (2024, 2): 455.97,
    (2024, 3): 514.32,
    (2024, 4): 640.58,
    (2025, 1): 710.86,
    (2025, 2): 796.10,
    (2025, 3): 881.56,
    (2025, 4): 951.68,
    (2026, 1): 959.10,
    (2026, 2): 935.70,
    (2026, 3): 373.72,
    (2026, 4): 0.00,
}

# Quarters still in progress — compare as minimum (computed >= reference partial).
PARTIAL_REFERENCE_QUARTERS: frozenset[tuple[int, int]] = frozenset({(2026, 3), (2026, 4)})

QUARTER_LABELS = ("Q1", "Q2", "Q3", "Q4")


def quarter_for_month(month: int) -> int:
    return (month - 1) // 3 + 1


def quarterly_gross_from_monthly_records(
    records: list[MonthlyNetDividend],
) -> dict[tuple[int, int], float]:
    """Sum monthly gross USD into calendar quarters."""
    totals: dict[tuple[int, int], float] = {}
    for item in records:
        key = (item.year, quarter_for_month(item.month))
        totals[key] = round(totals.get(key, 0.0) + item.gross_usd, 2)
    return totals


def quarterly_gross_from_receipt_store(receipt_store: Any) -> dict[tuple[int, int], float]:
    """All imported/synced receipts — includes sold tickers (income history scope)."""
    return receipt_store.quarterly_gross_totals()


def pivot_quarterly_gross_dataframe(
    totals: dict[tuple[int, int], float],
    *,
    years: list[int] | None = None,
) -> pd.DataFrame:
    """Rows = Q1–Q4, columns = years (spreadsheet-style)."""
    if not totals:
        return pd.DataFrame()

    all_years = years or sorted({year for year, _quarter in totals})
    matrix: dict[str, dict[int, float | None]] = {
        label: dict.fromkeys(all_years) for label in QUARTER_LABELS
    }
    for (year, quarter), gross in totals.items():
        matrix[QUARTER_LABELS[quarter - 1]][year] = gross

    rows: list[dict[str, Any]] = []
    for label in QUARTER_LABELS:
        row: dict[str, Any] = {"Quarter": label}
        for year in all_years:
            row[str(year)] = matrix[label][year]
        rows.append(row)
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class QuarterComparisonRow:
    year: int
    quarter: int
    reference_usd: float
    computed_usd: float
    delta_usd: float
    status: str  # match | mismatch | partial | missing


def compare_quarterly_gross(
    computed: dict[tuple[int, int], float],
    reference: dict[tuple[int, int], float] | None = None,
    *,
    tolerance_usd: float = 1.0,
) -> list[QuarterComparisonRow]:
    """Compare computed quarterly gross against IBKR reference values."""
    reference = reference or IBKR_REFERENCE_QUARTERLY_GROSS
    keys = sorted(set(reference) | set(computed))
    rows: list[QuarterComparisonRow] = []

    for year, quarter in keys:
        ref = reference.get((year, quarter))
        comp = computed.get((year, quarter), 0.0)
        if ref is None:
            if comp <= 0:
                continue
            rows.append(
                QuarterComparisonRow(
                    year=year,
                    quarter=quarter,
                    reference_usd=0.0,
                    computed_usd=comp,
                    delta_usd=comp,
                    status="extra",
                )
            )
            continue

        delta = round(comp - ref, 2)
        if (year, quarter) in PARTIAL_REFERENCE_QUARTERS:
            status = "partial" if comp + tolerance_usd >= ref else "mismatch"
        elif abs(delta) <= tolerance_usd or (comp <= 0 and ref <= 0):
            status = "match"
        else:
            status = "mismatch"

        rows.append(
            QuarterComparisonRow(
                year=year,
                quarter=quarter,
                reference_usd=ref,
                computed_usd=comp,
                delta_usd=delta,
                status=status,
            )
        )
    return rows


@dataclass(frozen=True)
class AnnualNetComparisonRow:
    year: int
    reference_usd: float
    computed_usd: float
    delta_usd: float
    status: str  # match | mismatch | partial


def compare_annual_net(
    computed: dict[int, float],
    reference: dict[int, float] | None = None,
    *,
    tolerance_usd: float = 1.0,
    through: date | None = None,
) -> list[AnnualNetComparisonRow]:
    """Compare computed annual net dividends against IBKR reference values."""
    reference = reference or IBKR_REFERENCE_ANNUAL_NET
    through = through or IBKR_REFERENCE_THROUGH_DATE
    keys = sorted(set(reference) | set(computed))
    rows: list[AnnualNetComparisonRow] = []

    for year in keys:
        ref = reference.get(year)
        comp = computed.get(year, 0.0)
        if ref is None:
            if comp <= 0:
                continue
            rows.append(
                AnnualNetComparisonRow(
                    year=year,
                    reference_usd=0.0,
                    computed_usd=comp,
                    delta_usd=comp,
                    status="extra",
                )
            )
            continue

        delta = round(comp - ref, 2)
        partial_year = year == through.year
        if partial_year:
            status = "partial" if comp + tolerance_usd >= ref else "mismatch"
        elif abs(delta) <= tolerance_usd or (comp <= 0 and ref <= 0):
            status = "match"
        else:
            status = "mismatch"

        rows.append(
            AnnualNetComparisonRow(
                year=year,
                reference_usd=ref,
                computed_usd=comp,
                delta_usd=delta,
                status=status,
            )
        )
    return rows
