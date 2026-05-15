"""Tests for portfolio risk monitor serialization and staleness."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from services.portfolio_attention_service import AttentionItem, AttentionSummary
from services.portfolio_risk_monitor_service import PortfolioRiskMonitorService


def test_is_stale_when_never_checked():
    assert PortfolioRiskMonitorService.is_stale(None) is True


def test_is_stale_within_interval():
    now = datetime(2026, 5, 13, 12, 0, 0)
    checked = now - timedelta(minutes=30)
    assert (
        PortfolioRiskMonitorService.is_stale(
            checked, interval_seconds=3600, now=now
        )
        is False
    )


def test_is_stale_after_interval():
    now = datetime(2026, 5, 13, 12, 0, 0)
    checked = now - timedelta(hours=2)
    assert (
        PortfolioRiskMonitorService.is_stale(
            checked, interval_seconds=3600, now=now
        )
        is True
    )


def test_summary_round_trip():
    item = AttentionItem(
        symbol="ARE",
        company="Alexandria",
        severity="high",
        score=55,
        categories=("Exposure", "Estimates"),
        reasons=("Large unrealized loss", "Analyst view: AVOID"),
        portfolio_weight_pct=9.5,
        profit_pct=-22.0,
    )
    summary = AttentionSummary(
        items=[item],
        reference_date=date(2026, 5, 13),
    )
    stored = PortfolioRiskMonitorService.summary_to_store(summary)
    restored = PortfolioRiskMonitorService.summary_from_store(stored)
    assert restored is not None
    assert restored.total == 1
    assert restored.items[0].symbol == "ARE"
    assert restored.items[0].categories == ("Exposure", "Estimates")
    assert restored.reference_date == date(2026, 5, 13)
