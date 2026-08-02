"""Quarterly dividend gross totals vs IBKR reference."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from pathlib import Path

from data_ingestion.dividend_income_store import MONTH_LABELS, MonthlyNetDividend
from data_ingestion.dividend_receipt_store import DividendReceiptStore
from services.portfolio_dividend_quarters import (
    IBKR_REFERENCE_ANNUAL_NET,
    IBKR_REFERENCE_QUARTERLY_GROSS,
    compare_annual_net,
    compare_quarterly_gross,
    pivot_quarterly_gross_dataframe,
    quarter_for_month,
    quarterly_gross_from_monthly_records,
    quarterly_gross_from_receipt_store,
)


def test_quarter_for_month() -> None:
    assert quarter_for_month(1) == 1
    assert quarter_for_month(3) == 1
    assert quarter_for_month(4) == 2
    assert quarter_for_month(12) == 4


def test_quarterly_gross_from_monthly_records() -> None:
    records = [
        MonthlyNetDividend(
            period=date(2025, 1, 1),
            year=2025,
            month=1,
            month_label=MONTH_LABELS[0],
            net_usd=90.0,
            tax_rate_pct=10.0,
            gross_usd=100.0,
            tax_withheld_usd=10.0,
        ),
        MonthlyNetDividend(
            period=date(2025, 2, 1),
            year=2025,
            month=2,
            month_label=MONTH_LABELS[1],
            net_usd=45.0,
            tax_rate_pct=10.0,
            gross_usd=50.0,
            tax_withheld_usd=5.0,
        ),
        MonthlyNetDividend(
            period=date(2025, 4, 1),
            year=2025,
            month=4,
            month_label=MONTH_LABELS[3],
            net_usd=180.0,
            tax_rate_pct=10.0,
            gross_usd=200.0,
            tax_withheld_usd=20.0,
        ),
    ]
    totals = quarterly_gross_from_monthly_records(records)
    assert totals[(2025, 1)] == 150.0
    assert totals[(2025, 2)] == 200.0


def test_quarterly_gross_from_receipt_store(tmp_path: Path) -> None:
    store = DividendReceiptStore(tmp_path / "portfolio.db")
    store.sync_receipt(
        "KO",
        ex_date=date(2025, 3, 10),
        pay_date=date(2025, 3, 15),
        per_share_usd=0.5,
        shares_held=10.0,
        gross_usd=5.0,
        source="ibkr",
    )
    store.sync_receipt(
        "PEP",
        ex_date=date(2025, 5, 10),
        pay_date=date(2025, 5, 20),
        per_share_usd=1.0,
        shares_held=8.0,
        gross_usd=8.0,
        source="ibkr",
    )
    store.sync_receipt(
        "VZ",
        ex_date=date(2024, 11, 10),
        pay_date=date(2024, 11, 25),
        per_share_usd=0.67,
        shares_held=5.0,
        gross_usd=3.35,
        source="ibkr",
    )

    totals = quarterly_gross_from_receipt_store(store)
    assert totals[(2025, 1)] == 5.0
    assert totals[(2025, 2)] == 8.0
    assert totals[(2024, 4)] == 3.35


def test_pivot_quarterly_gross_dataframe() -> None:
    pivot = pivot_quarterly_gross_dataframe({(2025, 1): 100.0, (2025, 4): 200.0})
    assert list(pivot["Quarter"]) == ["Q1", "Q2", "Q3", "Q4"]
    assert pivot.loc[pivot["Quarter"] == "Q1", "2025"].iloc[0] == 100.0
    assert pivot.loc[pivot["Quarter"] == "Q4", "2025"].iloc[0] == 200.0


def test_compare_quarterly_gross_detects_mismatch() -> None:
    computed = {(2025, 1): 700.0, (2025, 2): 796.10}
    reference = {(2025, 1): 710.86, (2025, 2): 796.10}
    rows = compare_quarterly_gross(computed, reference, tolerance_usd=1.0)
    q1 = next(row for row in rows if row.year == 2025 and row.quarter == 1)
    q2 = next(row for row in rows if row.year == 2025 and row.quarter == 2)
    assert q1.status == "mismatch"
    assert q2.status == "match"


def test_reference_quarterly_totals_sum_sensibly() -> None:
    """Sanity check — reference table grows with portfolio scale."""
    y2025 = sum(
        gross for (year, _quarter), gross in IBKR_REFERENCE_QUARTERLY_GROSS.items() if year == 2025
    )
    y2023 = sum(
        gross for (year, _quarter), gross in IBKR_REFERENCE_QUARTERLY_GROSS.items() if year == 2023
    )
    assert y2025 > y2023


def test_compare_annual_net_matches_reference() -> None:
    rows = compare_annual_net(IBKR_REFERENCE_ANNUAL_NET, IBKR_REFERENCE_ANNUAL_NET)
    assert all(row.status in {"match", "partial"} for row in rows)


def test_compare_annual_net_detects_mismatch() -> None:
    computed = {2024: 2000.0, 2025: 3340.20}
    rows = compare_annual_net(computed, tolerance_usd=1.0)
    y2024 = next(row for row in rows if row.year == 2024)
    y2025 = next(row for row in rows if row.year == 2025)
    assert y2024.status == "mismatch"
    assert y2025.status == "match"
