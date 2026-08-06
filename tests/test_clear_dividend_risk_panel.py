"""Tests for Clear Dividend Risk holding evidence UI helpers (PR 2)."""
# ruff: noqa: S101

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from services.clear_dividend_risk import (
    METHODOLOGY_VERSION,
    ConfidenceLevel,
    DividendRiskEvidence,
    RiskLevel,
    SecurityType,
    assess_holding_dividend_risk,
)
from ui.clear_dividend_risk_panel import (
    DISCLAIMER,
    assess_holding_for_ui,
    confidence_label,
    evidence_table_rows,
    format_as_of,
    format_income,
    primary_signal_messages,
    resolve_estimated_annual_income,
)
from ui.design_system import _health_panel_markup, status_class_for_label


def test_status_labels_map_to_design_tokens() -> None:
    assert status_class_for_label("Lower observed risk") == "healthy"
    assert status_class_for_label("Monitor") == "watch"
    assert status_class_for_label("High observed risk") == "risky"
    assert status_class_for_label("Insufficient data") == "unknown"
    assert status_class_for_label("Special analysis required") == "unknown"
    assert status_class_for_label("High") == "confirmed"
    assert status_class_for_label("Medium") == "watch"
    assert status_class_for_label("Low") == "unknown"


def test_health_panel_title_uses_sustainability() -> None:
    markup = _health_panel_markup(
        "Monitor",
        ("FCF payout is 88%.",),
        title="Dividend sustainability",
    )
    assert "Dividend sustainability · Monitor" in markup
    assert "FCF payout is 88%." in markup


def test_assess_holding_for_ui_prefers_document_evidence() -> None:
    doc = SimpleNamespace(
        symbol="KO",
        name="Coca-Cola",
        sector="Consumer Staples",
        industry="Beverages",
        annual_dividend=1.84,
        payout_ratio=55.0,
        fcf_payout_ratio=60.0,
        dividend_coverage=1.8,
        dividend_cagr_5y=4.0,
        dividend_history=[],
        last_updated=date(2026, 6, 30),
        source=SimpleNamespace(value="yahoo"),
    )
    result = assess_holding_for_ui(symbol="KO", vector_doc=doc, today=date(2026, 8, 6))
    assert result.risk_level is RiskLevel.LOWER_OBSERVED_RISK
    assert result.methodology_version == METHODOLOGY_VERSION
    assert result.data_as_of == date(2026, 6, 30)


def test_primary_signals_and_evidence_rows() -> None:
    assessment = assess_holding_dividend_risk(
        DividendRiskEvidence(
            symbol="X",
            security_type=SecurityType.STANDARD,
            annual_dividend=1.0,
            fcf_payout_ratio=88.0,
            earnings_payout_ratio=55.0,
            dividend_coverage=1.5,
            data_as_of=date(2026, 6, 30),
            source_names=("yahoo",),
        ),
        today=date(2026, 8, 6),
    )
    messages = primary_signal_messages(assessment)
    assert messages
    assert "88" in messages[0]
    rows = evidence_table_rows(assessment)
    labels = [label for label, _ in rows]
    assert "Dividend sustainability" in labels
    assert "Methodology" in labels
    assert any(label.startswith("Signal ·") for label in labels)
    assert DISCLAIMER
    assert "not financial advice" in DISCLAIMER.lower()
    assert "does not recommend buying, selling, or holding" in DISCLAIMER.lower()


def test_build_portfolio_clear_dividend_risk_summary() -> None:
    from types import SimpleNamespace

    from ui.clear_dividend_risk_panel import (
        build_portfolio_clear_dividend_risk,
        concentration_label,
        portfolio_income_metric_items,
        portfolio_table_records,
    )

    rows = [
        SimpleNamespace(
            ticker="KO",
            company="Coca-Cola",
            shares=10.0,
            annual_income=400.0,
            sector="Consumer Staples",
        ),
        SimpleNamespace(
            ticker="HI",
            company="High Risk Co",
            shares=5.0,
            annual_income=600.0,
            sector="Energy",
        ),
    ]
    docs = {
        "KO": SimpleNamespace(
            symbol="KO",
            name="Coca-Cola",
            sector="Consumer Staples",
            industry="Beverages",
            annual_dividend=1.84,
            payout_ratio=55.0,
            fcf_payout_ratio=60.0,
            dividend_coverage=1.8,
            dividend_cagr_5y=4.0,
            dividend_history=[],
            last_updated=date(2026, 6, 30),
            source=SimpleNamespace(value="yahoo"),
        ),
        "HI": SimpleNamespace(
            symbol="HI",
            name="High Risk Co",
            sector="Energy",
            industry="Oil",
            annual_dividend=2.0,
            payout_ratio=55.0,
            fcf_payout_ratio=130.0,
            dividend_coverage=1.2,
            dividend_cagr_5y=1.0,
            dividend_history=[],
            last_updated=date(2026, 6, 30),
            source=SimpleNamespace(value="yahoo"),
        ),
    }
    view = build_portfolio_clear_dividend_risk(
        rows,
        vector_docs=docs,
        today=date(2026, 8, 6),
    )
    portfolio = view.portfolio
    assert portfolio.total_estimated_annual_income == 1000.0
    assert portfolio.income_elevated_risk == 600.0
    assert portfolio.income_by_risk_level[RiskLevel.HIGH_OBSERVED_RISK.value] == 600.0
    assert portfolio.income_by_risk_level[RiskLevel.LOWER_OBSERVED_RISK.value] == 400.0
    assert portfolio.company_concentration.value in {"MONITOR", "HIGH"}
    assert portfolio.largest_income_contributor is not None
    assert portfolio.largest_income_contributor[0] == "HI"
    assert view.table_rows[0].symbol == "HI"
    assert view.table_rows[0].action == "Review evidence"
    assert view.table_rows[0].sustainability_status == "High observed risk"
    assert view.alerts  # high FCF payout + concentration from HI at 60%

    metrics = portfolio_income_metric_items(portfolio)
    labels = [item[0] for item in metrics]
    assert "Estimated income exposed to elevated dividend risk" in labels
    assert "risk-adjusted" not in " ".join(labels).lower()

    records = portfolio_table_records(view.table_rows)
    assert records[0]["Action"] == "Review evidence"
    assert "Sustainability" in records[0]
    assert concentration_label(portfolio.company_concentration)


def test_format_helpers_and_income_resolution() -> None:
    assert format_as_of(date(2026, 6, 30)) == "June 30, 2026"
    assert format_as_of(None) == "Not available"
    assert format_income(240.0) == "$240"
    assert format_income(None) == "Not available"
    assert confidence_label(ConfidenceLevel.MEDIUM) == "Medium"

    rows = [SimpleNamespace(ticker="KO", annual_income=240.0)]
    assert resolve_estimated_annual_income("ko", portfolio_rows=rows) == 240.0
    assert resolve_estimated_annual_income("KO", estimated_annual_income=99.0) == 99.0
    assert resolve_estimated_annual_income("MSFT", portfolio_rows=rows) is None
