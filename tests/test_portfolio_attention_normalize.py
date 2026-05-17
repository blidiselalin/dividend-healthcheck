"""Tests for attention summary normalization and legacy cache shapes."""

from __future__ import annotations

from datetime import date

from services.portfolio_attention_service import (
    AttentionItem,
    AttentionSummary,
    normalize_attention_summary,
)
from services.portfolio_risk_monitor_service import PortfolioRiskMonitorService


def _item(symbol: str = "TST") -> AttentionItem:
    return AttentionItem(
        symbol=symbol,
        company="Test",
        severity="medium",
        score=40,
        categories=("Exposure",),
        reasons=("Test reason",),
        portfolio_weight_pct=5.0,
        profit_pct=-5.0,
    )


def test_normalize_none_returns_none() -> None:
    assert normalize_attention_summary(None) is None


def test_normalize_modern_summary_round_trip() -> None:
    summary = AttentionSummary(
        risk_items=[_item("R")],
        dividend_items=[_item("D")],
        reference_date=date(2026, 5, 1),
    )
    normalized = normalize_attention_summary(summary)
    assert normalized is not None
    assert len(normalized.risk_items) == 1
    assert len(normalized.dividend_items) == 1


def test_normalize_dict_uses_risk_monitor_store() -> None:
    summary = AttentionSummary(
        risk_items=[_item("KO")],
        dividend_items=[],
        reference_date=date(2026, 5, 1),
    )
    stored = PortfolioRiskMonitorService.summary_to_store(summary)
    restored = normalize_attention_summary(stored)
    assert restored is not None
    assert restored.total == 1
    assert restored.items[0].symbol == "KO"


def test_normalize_legacy_items_property() -> None:
    legacy = AttentionSummary(
        risk_items=[_item("LEG")],
        reference_date=date(2026, 1, 1),
    )
    normalized = normalize_attention_summary(legacy)
    assert normalized is not None
    assert normalized.risk_items[0].symbol == "LEG"
