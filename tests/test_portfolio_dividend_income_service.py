"""Tests for portfolio dividend income service."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from data_ingestion.dividend_income_store import MonthlyNetDividend
from services.portfolio_dividend_income_service import PortfolioDividendIncomeService


def _record(*, year: int, month: int, net: float, gross: float, tax: float) -> MonthlyNetDividend:
    return MonthlyNetDividend(
        period=date(year, month, 1),
        year=year,
        month=month,
        month_label=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month - 1],
        net_usd=net,
        tax_rate_pct=tax,
        gross_usd=gross,
        tax_withheld_usd=round(gross - net, 2),
    )


def test_summarize_with_rows_uses_estimated_annual_net() -> None:
    service = PortfolioDividendIncomeService(store=SimpleNamespace(list_dividends=lambda: []))
    records = [
        _record(year=2025, month=12, net=90.0, gross=100.0, tax=10.0),
        _record(year=2026, month=1, net=84.0, gross=100.0, tax=16.0),
        _record(year=2026, month=2, net=168.0, gross=200.0, tax=16.0),
    ]

    # 360 annual gross -> 16% tax in 2026 => 302.4 net annual => 25.2 monthly
    rows = [SimpleNamespace(annual_income=120.0), SimpleNamespace(annual_income=240.0)]
    summary = service.summarize(records=records, ytd_year=2026, rows=rows)

    assert summary.total_net_usd == 342.0
    assert summary.ytd_year == 2026
    assert summary.ytd_net_usd == 252.0
    assert summary.best_year == 2026
    assert summary.best_year_net == 252.0
    assert summary.avg_monthly_net == 25.2
    assert summary.month_count == 3


def test_pivot_and_timeline_dataframes() -> None:
    service = PortfolioDividendIncomeService(store=SimpleNamespace(list_dividends=lambda: []))
    records = [
        _record(year=2025, month=12, net=90.0, gross=100.0, tax=10.0),
        _record(year=2026, month=1, net=84.0, gross=100.0, tax=16.0),
        _record(year=2026, month=2, net=168.0, gross=200.0, tax=16.0),
    ]

    pivot = service.pivot_net_dataframe(records)
    assert list(pivot.columns) == ["Month", "2025", "2026"]
    assert pivot[pivot["Month"] == "Jan"].iloc[0]["2026"] == 84.0
    assert pivot[pivot["Month"] == "Dec"].iloc[0]["2025"] == 90.0

    timeline = service.timeline_dataframe(records)
    assert list(timeline["label"]) == ["Dec 2025", "Jan 2026", "Feb 2026"]
    assert list(timeline["cumulative_net_usd"]) == [90.0, 174.0, 342.0]
