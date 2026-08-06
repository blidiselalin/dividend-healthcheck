"""
Read-only Clear Dividend Risk evidence audit.

Does not write to the database or call external providers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from services.clear_dividend_risk import (
    HoldingDividendRiskAssessment,
    assess_holding_dividend_risk,
    evidence_from_stock_document,
    load_risk_evidence_batch,
)


@dataclass(frozen=True)
class DividendRiskAuditRow:
    symbol: str
    market_document_found: bool
    security_type: str | None
    annual_dividend: float | None
    payout_ratio_pct: float | None
    fcf_payout_ratio_pct: float | None
    raw_free_cash_flow: float | None
    dividend_history_count: int
    latest_dividend_date: date | None
    source_names: tuple[str, ...]
    fundamentals_period_end: date | None
    document_updated_at: date | None
    missing_fields: tuple[str, ...]
    assessment_level: str | None
    assessment_confidence: str | None
    assessment_summary: str | None = None


def audit_dividend_risk_symbols(
    symbols: Sequence[str],
    *,
    today: date | None = None,
) -> list[DividendRiskAuditRow]:
    """Batch-load documents and report evidence + assessment (read-only)."""
    wanted = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    evidence_map = load_risk_evidence_batch(wanted)
    rows: list[DividendRiskAuditRow] = []
    for symbol in wanted:
        evidence = evidence_map.get(symbol)
        if evidence is None:
            rows.append(
                DividendRiskAuditRow(
                    symbol=symbol,
                    market_document_found=False,
                    security_type=None,
                    annual_dividend=None,
                    payout_ratio_pct=None,
                    fcf_payout_ratio_pct=None,
                    raw_free_cash_flow=None,
                    dividend_history_count=0,
                    latest_dividend_date=None,
                    source_names=(),
                    fundamentals_period_end=None,
                    document_updated_at=None,
                    missing_fields=("market_document",),
                    assessment_level=None,
                    assessment_confidence=None,
                    assessment_summary="Market document not found.",
                )
            )
            continue

        assessment: HoldingDividendRiskAssessment = assess_holding_dividend_risk(
            evidence, today=today
        )
        rows.append(
            DividendRiskAuditRow(
                symbol=symbol,
                market_document_found=True,
                security_type=evidence.security_type.value,
                annual_dividend=evidence.annual_dividend,
                payout_ratio_pct=evidence.earnings_payout_ratio,
                fcf_payout_ratio_pct=evidence.fcf_payout_ratio,
                raw_free_cash_flow=evidence.raw_free_cash_flow,
                dividend_history_count=len(evidence.dividend_payments),
                latest_dividend_date=evidence.dividend_history_through,
                source_names=evidence.source_names,
                fundamentals_period_end=evidence.fundamentals_period_end,
                document_updated_at=evidence.document_updated_at,
                missing_fields=assessment.missing_fields,
                assessment_level=assessment.risk_level.value,
                assessment_confidence=assessment.confidence.value,
                assessment_summary=assessment.summary,
            )
        )
    return rows


def format_audit_rows(rows: Sequence[DividendRiskAuditRow]) -> str:
    lines: list[str] = []
    for row in rows:
        payload = asdict(row)
        lines.append(f"=== {row.symbol} ===")
        for key, value in payload.items():
            if key == "symbol":
                continue
            lines.append(f"{key}: {value}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def audit_document_mapping(doc: Any) -> DividendRiskAuditRow:
    """Map one already-loaded document (tests / diagnostics)."""
    evidence = evidence_from_stock_document(doc)
    assessment = assess_holding_dividend_risk(evidence)
    return DividendRiskAuditRow(
        symbol=evidence.symbol,
        market_document_found=True,
        security_type=evidence.security_type.value,
        annual_dividend=evidence.annual_dividend,
        payout_ratio_pct=evidence.earnings_payout_ratio,
        fcf_payout_ratio_pct=evidence.fcf_payout_ratio,
        raw_free_cash_flow=evidence.raw_free_cash_flow,
        dividend_history_count=len(evidence.dividend_payments),
        latest_dividend_date=evidence.dividend_history_through,
        source_names=evidence.source_names,
        fundamentals_period_end=evidence.fundamentals_period_end,
        document_updated_at=evidence.document_updated_at,
        missing_fields=assessment.missing_fields,
        assessment_level=assessment.risk_level.value,
        assessment_confidence=assessment.confidence.value,
        assessment_summary=assessment.summary,
    )
