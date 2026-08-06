"""Clear Dividend Risk evidence mapping + audit (insufficient-data fix PR 1)."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from data_ingestion.models import DividendRecord
from services.clear_dividend_risk import (
    ConfidenceLevel,
    RiskLevel,
    SecurityType,
    assess_holding_dividend_risk,
    evidence_from_stock_document,
    infer_security_type,
    load_risk_evidence_batch,
)
from services.dividend_risk_audit import audit_dividend_risk_symbols, audit_document_mapping


def _payments(*amounts: tuple[date, float]) -> list[DividendRecord]:
    return [
        DividendRecord(ex_date=ex, payment_date=None, amount=amount, frequency="quarterly")
        for ex, amount in amounts
    ]


def _doc(**overrides) -> SimpleNamespace:
    base = {
        "symbol": "PEP",
        "name": "PepsiCo",
        "sector": "",
        "industry": "Unknown",
        "annual_dividend": 5.69,
        "payout_ratio": 75.0,
        "fcf_payout_ratio": 68.0,
        "dividend_coverage": 1.4,
        "dividend_cagr_5y": 7.0,
        "dividend_history": _payments(
            (date(2024, 3, 1), 1.27),
            (date(2024, 6, 1), 1.27),
            (date(2024, 9, 1), 1.27),
            (date(2024, 12, 1), 1.27),
            (date(2025, 3, 1), 1.36),
            (date(2025, 6, 1), 1.36),
        ),
        "last_updated": datetime(2026, 8, 6, 12, 0, 0),
        "source": SimpleNamespace(value="yahoo"),
        "free_cash_flow": None,
        "affo_payout_ratio": None,
        "ffo_payout_ratio": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_stored_payout_and_fcf_reach_risk_input() -> None:
    evidence = evidence_from_stock_document(_doc(payout_ratio=82.0, fcf_payout_ratio=91.0))
    assert evidence.earnings_payout_ratio == 82.0
    assert evidence.fcf_payout_ratio == 91.0
    result = assess_holding_dividend_risk(evidence, today=date(2026, 8, 6))
    assert result.observed_values["earnings_payout_ratio"] == 82.0
    assert result.observed_values["fcf_payout_ratio"] == 91.0
    assert result.risk_level is RiskLevel.MONITOR


def test_negative_fcf_remains_valid_evidence() -> None:
    evidence = evidence_from_stock_document(
        _doc(fcf_payout_ratio=None, free_cash_flow=-1_000_000.0)
    )
    assert evidence.raw_free_cash_flow == -1_000_000.0
    assert evidence.fcf_zero_or_undefined is True
    result = assess_holding_dividend_risk(evidence, today=date(2026, 8, 6))
    assert result.risk_level is RiskLevel.HIGH_OBSERVED_RISK


def test_zero_fcf_does_not_raise() -> None:
    evidence = evidence_from_stock_document(_doc(fcf_payout_ratio=None, free_cash_flow=0.0))
    result = assess_holding_dividend_risk(evidence, today=date(2026, 8, 6))
    assert result.risk_level is RiskLevel.HIGH_OBSERVED_RISK


def test_dividend_history_reaches_risk_input() -> None:
    evidence = evidence_from_stock_document(_doc())
    assert len(evidence.dividend_payments) == 6
    assert evidence.dividend_history_through == date(2025, 6, 1)
    assert evidence.document_updated_at == date(2026, 8, 6)


def test_one_coverage_metric_allows_medium_confidence_assessment() -> None:
    evidence = evidence_from_stock_document(
        _doc(
            payout_ratio=55.0,
            fcf_payout_ratio=None,
            dividend_coverage=None,
            free_cash_flow=None,
        )
    )
    result = assess_holding_dividend_risk(evidence, today=date(2026, 8, 6))
    assert result.risk_level is not RiskLevel.INSUFFICIENT_DATA
    assert result.confidence is ConfidenceLevel.MEDIUM


def test_no_coverage_metrics_returns_insufficient_data() -> None:
    evidence = evidence_from_stock_document(
        _doc(
            payout_ratio=None,
            fcf_payout_ratio=None,
            dividend_coverage=None,
            free_cash_flow=None,
        )
    )
    result = assess_holding_dividend_risk(evidence, today=date(2026, 8, 6))
    assert result.risk_level is RiskLevel.INSUFFICIENT_DATA
    assert "Unable to assess" in result.summary
    assert "payout coverage" in result.summary
    assert "free-cash-flow coverage" in result.summary
    assert "fcf_payout_ratio" in result.missing_fields
    assert "earnings_payout_ratio" in result.missing_fields


def test_reit_without_affo_special_analysis_not_insufficient() -> None:
    for symbol in ("O", "ARE", "AMT"):
        evidence = evidence_from_stock_document(
            _doc(
                symbol=symbol,
                name=symbol,
                sector="",
                industry="Unknown",
                payout_ratio=120.0,
                fcf_payout_ratio=95.0,
            )
        )
        assert evidence.security_type is SecurityType.REIT
        result = assess_holding_dividend_risk(evidence, today=date(2026, 8, 6))
        assert result.risk_level is RiskLevel.SPECIAL_ANALYSIS_REQUIRED
        assert result.confidence is ConfidenceLevel.LOW
        assert "AFFO" in result.summary or "FFO" in result.summary
        assert result.risk_level is not RiskLevel.INSUFFICIENT_DATA


def test_known_standard_symbols_use_standard_model() -> None:
    assert infer_security_type(symbol="PEP", sector="", industry="Unknown") is SecurityType.STANDARD
    evidence = evidence_from_stock_document(_doc(symbol="PEP", sector="", industry="Unknown"))
    result = assess_holding_dividend_risk(evidence, today=date(2026, 8, 6))
    assert result.risk_level is RiskLevel.LOWER_OBSERVED_RISK


def test_batch_loading_multiple_symbols() -> None:
    docs = {
        "PEP": _doc(symbol="PEP"),
        "MO": _doc(symbol="MO", payout_ratio=70.0),
        "O": _doc(symbol="O", name="Realty Income"),
    }
    with patch("services.shared_market_db.load_documents", return_value=docs) as mocked:
        evidence = load_risk_evidence_batch(["pep", "mo", "o"])
    mocked.assert_called_once()
    assert set(evidence) == {"PEP", "MO", "O"}
    assert evidence["O"].security_type is SecurityType.REIT


def test_missing_fields_identify_real_gaps() -> None:
    row = audit_document_mapping(
        _doc(
            payout_ratio=None,
            fcf_payout_ratio=None,
            dividend_coverage=None,
            dividend_history=[],
            free_cash_flow=None,
        )
    )
    assert "earnings_payout_ratio" in row.missing_fields
    assert "fcf_payout_ratio" in row.missing_fields
    assert "dividend_history" in row.missing_fields
    assert row.assessment_level == RiskLevel.INSUFFICIENT_DATA.value


def test_audit_symbols_read_only_batch() -> None:
    docs = {"PEP": _doc(symbol="PEP"), "O": _doc(symbol="O")}
    with patch("services.shared_market_db.load_documents", return_value=docs):
        rows = audit_dividend_risk_symbols(["PEP", "O", "ZZZZ"])
    by_symbol = {row.symbol: row for row in rows}
    assert by_symbol["PEP"].market_document_found is True
    assert by_symbol["PEP"].payout_ratio_pct == 75.0
    assert by_symbol["O"].security_type == SecurityType.REIT.value
    assert by_symbol["O"].assessment_level == RiskLevel.SPECIAL_ANALYSIS_REQUIRED.value
    assert by_symbol["ZZZZ"].market_document_found is False
