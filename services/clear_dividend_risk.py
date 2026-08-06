"""
Clear Dividend Risk — explainable, evidence-based dividend sustainability.

Pure assessment + high-value portfolio alerts (no persistence, no external API calls).

Three concepts stay separate:
1. Company dividend sustainability (status + signals)
2. Portfolio income concentration (company / sector)
3. Data confidence (freshness + completeness)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Final

METHODOLOGY_VERSION: Final[str] = "1.0"

# --- Threshold constants (single source; UI must import these) ---
DIVIDEND_CUT_MAJOR_PCT: Final[float] = 10.0
FCF_PAYOUT_MONITOR_MIN_PCT: Final[float] = 80.0
FCF_PAYOUT_HIGH_MIN_PCT: Final[float] = 100.0
EARNINGS_PAYOUT_MONITOR_MIN_PCT: Final[float] = 80.0
EARNINGS_PAYOUT_HIGH_MIN_PCT: Final[float] = 100.0
DATA_FRESHNESS_WARNING_DAYS: Final[int] = 120
DATA_STALE_LOW_CONFIDENCE_DAYS: Final[int] = 365
COMPANY_INCOME_CONCENTRATION_MONITOR_PCT: Final[float] = 25.0
COMPANY_INCOME_CONCENTRATION_HIGH_PCT: Final[float] = 40.0
SECTOR_INCOME_CONCENTRATION_MONITOR_PCT: Final[float] = 35.0
SECTOR_INCOME_CONCENTRATION_HIGH_PCT: Final[float] = 50.0
SPLIT_RATIO_TOLERANCE: Final[float] = 0.08
# Income share above which insufficient/stale evidence warrants a portfolio alert.
MATERIAL_INCOME_SHARE_PCT: Final[float] = 5.0

# Elevated company risk for portfolio income exposure (not concentration).
ELEVATED_RISK_LEVELS: Final[frozenset[str]] = frozenset({"MONITOR", "HIGH_OBSERVED_RISK"})


class RiskLevel(str, Enum):
    LOWER_OBSERVED_RISK = "LOWER_OBSERVED_RISK"
    MONITOR = "MONITOR"
    HIGH_OBSERVED_RISK = "HIGH_OBSERVED_RISK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    SPECIAL_ANALYSIS_REQUIRED = "SPECIAL_ANALYSIS_REQUIRED"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SecurityType(str, Enum):
    STANDARD = "STANDARD"
    REIT = "REIT"
    BANK_INSURER = "BANK_INSURER"
    ETF_FUND = "ETF_FUND"
    UNKNOWN = "UNKNOWN"


class ConcentrationLevel(str, Enum):
    NONE = "NONE"
    MONITOR = "MONITOR"
    HIGH = "HIGH"


RISK_LEVEL_LABELS: Final[dict[RiskLevel, str]] = {
    RiskLevel.LOWER_OBSERVED_RISK: "Lower observed risk",
    RiskLevel.MONITOR: "Monitor",
    RiskLevel.HIGH_OBSERVED_RISK: "High observed risk",
    RiskLevel.INSUFFICIENT_DATA: "Insufficient data",
    RiskLevel.SPECIAL_ANALYSIS_REQUIRED: "Special analysis required",
}

# Signal codes (stable for tests / UI)
SIGNAL_UNSUPPORTED_TYPE = "UNSUPPORTED_SECURITY_TYPE"
SIGNAL_REIT_MISSING_AFFO_FFO = "REIT_MISSING_AFFO_FFO"
SIGNAL_MISSING_CORE = "MISSING_CORE_EVIDENCE"
SIGNAL_DIVIDEND_CUT_MAJOR = "DIVIDEND_CUT_MAJOR"
SIGNAL_DIVIDEND_CUT_MINOR = "DIVIDEND_CUT_MINOR"
SIGNAL_DIVIDEND_SUSPENSION = "DIVIDEND_SUSPENSION"
SIGNAL_FCF_NEGATIVE = "FCF_NEGATIVE_WHILE_PAYING"
SIGNAL_FCF_PAYOUT_CRITICAL = "FCF_PAYOUT_ABOVE_100"
SIGNAL_FCF_PAYOUT_ELEVATED = "FCF_PAYOUT_80_TO_100"
SIGNAL_EARNINGS_NEGATIVE = "EPS_NEGATIVE_WHILE_PAYING"
SIGNAL_EARNINGS_PAYOUT_CRITICAL = "EARNINGS_PAYOUT_ABOVE_100"
SIGNAL_EARNINGS_PAYOUT_ELEVATED = "EARNINGS_PAYOUT_80_TO_100"
SIGNAL_FCF_NEGATIVE_STREAK = "FCF_NEGATIVE_TWO_PERIODS"
SIGNAL_FCF_DECLINING = "FCF_DECLINING_TWO_PERIODS"
SIGNAL_DIVIDEND_CAGR_NEGATIVE = "DIVIDEND_CAGR_NEGATIVE"
SIGNAL_DIVIDEND_NO_GROWTH = "DIVIDEND_NO_GROWTH_THREE_YEARS"
SIGNAL_DATA_FRESHNESS_WARNING = "DATA_FRESHNESS_WARNING"
SIGNAL_DATA_STALE = "DATA_STALE_LOW_CONFIDENCE"
SIGNAL_MISSING_AS_OF = "MISSING_AS_OF_DATE"
SIGNAL_CONFLICTING_COVERAGE = "CONFLICTING_COVERAGE_SOURCES"
SIGNAL_ZERO_DENOMINATOR = "ZERO_DENOMINATOR_COVERAGE"

# High-value portfolio alert codes (PR 4)
ALERT_DIVIDEND_SUSPENSION = "ALERT_DIVIDEND_SUSPENSION"
ALERT_DIVIDEND_CUT_MAJOR = "ALERT_DIVIDEND_CUT_MAJOR"
ALERT_FCF_NEGATIVE = "ALERT_FCF_NEGATIVE"
ALERT_COMPANY_INCOME_CONCENTRATION = "ALERT_COMPANY_INCOME_CONCENTRATION"
ALERT_MATERIAL_INSUFFICIENT_DATA = "ALERT_MATERIAL_INSUFFICIENT_DATA"
ALERT_MATERIAL_STALE_EVIDENCE = "ALERT_MATERIAL_STALE_EVIDENCE"


@dataclass(frozen=True)
class DividendPaymentEvidence:
    """One dividend payment; specials are ignored for cut detection."""

    ex_date: date
    amount: float
    frequency: str = "quarterly"


@dataclass(frozen=True)
class DividendRiskEvidence:
    """
    Normalized evidence for one holding.

    Callers batch-load market documents and map into this shape — assessment
    never hits external APIs.
    """

    symbol: str
    security_type: SecurityType = SecurityType.STANDARD
    sector: str | None = None
    industry: str | None = None
    name: str | None = None
    annual_dividend: float | None = None
    earnings_payout_ratio: float | None = None
    fcf_payout_ratio: float | None = None
    dividend_coverage: float | None = None
    # Comparable-period free cash flow, newest first (optional series).
    fcf_periods: tuple[float, ...] = ()
    affo_payout_ratio: float | None = None
    ffo_payout_ratio: float | None = None
    dividend_cagr_3y: float | None = None
    dividend_payments: tuple[DividendPaymentEvidence, ...] = ()
    data_as_of: date | None = None
    source_names: tuple[str, ...] = ()
    # Explicit flags when series inference is provided by the caller.
    fcf_zero_or_undefined: bool = False


@dataclass(frozen=True)
class RiskSignal:
    code: str
    severity: str  # high | monitor | info | confidence
    message: str
    observed_value: float | None = None
    threshold_description: str | None = None
    source_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class HoldingDividendRiskAssessment:
    symbol: str
    risk_level: RiskLevel
    risk_label: str
    confidence: ConfidenceLevel
    summary: str
    risk_signals: tuple[RiskSignal, ...]
    observed_values: dict[str, Any]
    threshold_descriptions: dict[str, str]
    missing_fields: tuple[str, ...]
    source_names: tuple[str, ...]
    data_as_of: date | None
    methodology_version: str = METHODOLOGY_VERSION


@dataclass(frozen=True)
class PortfolioHoldingIncomeInput:
    symbol: str
    estimated_annual_income: float
    sector: str | None = None
    assessment: HoldingDividendRiskAssessment | None = None


@dataclass(frozen=True)
class PortfolioDividendIncomeRisk:
    total_estimated_annual_income: float
    income_by_risk_level: dict[str, float]
    income_elevated_risk: float
    largest_income_contributor: tuple[str, float, float] | None
    largest_sector_income: tuple[str, float, float] | None
    company_concentration: ConcentrationLevel
    sector_concentration: ConcentrationLevel
    holdings: tuple[PortfolioHoldingIncomeInput, ...] = ()
    methodology_version: str = METHODOLOGY_VERSION


@dataclass(frozen=True)
class DividendRiskAlert:
    """High-value portfolio alert — educational, not a trade recommendation."""

    code: str
    severity: str  # high | monitor
    title: str
    message: str
    symbols: tuple[str, ...] = ()
    observed_value: float | None = None
    methodology_version: str = METHODOLOGY_VERSION


def risk_level_label(level: RiskLevel) -> str:
    return RISK_LEVEL_LABELS[level]


def infer_security_type(
    *,
    sector: str | None = None,
    industry: str | None = None,
    name: str | None = None,
    explicit: SecurityType | None = None,
) -> SecurityType:
    """Infer security type from classification text when quote type is absent."""
    if explicit is not None and explicit is not SecurityType.UNKNOWN:
        return explicit

    sector_l = (sector or "").strip().lower()
    industry_l = (industry or "").strip().lower()
    name_l = (name or "").strip().lower()
    blob = f"{sector_l} {industry_l} {name_l}"

    if any(
        token in blob for token in (" etf", "etf ", "exchange traded", " mutual fund", "index fund")
    ):
        return SecurityType.ETF_FUND
    if name_l.endswith(" etf") or " etf)" in name_l or industry_l == "etf":
        return SecurityType.ETF_FUND
    if "reit" in blob or industry_l.startswith("reit") or "real estate investment trust" in blob:
        return SecurityType.REIT
    if sector_l == "real estate" and "reit" in industry_l:
        return SecurityType.REIT
    if any(
        token in blob
        for token in (
            "bank",
            "banks",
            "insurance",
            "insurer",
            "life insurance",
            "property & casualty",
            "property and casualty",
        )
    ) and (
        "financial" in sector_l
        or "financial" in industry_l
        or "bank" in industry_l
        or "insurance" in industry_l
    ):
        return SecurityType.BANK_INSURER

    if (not sector_l or sector_l == "unknown") and (not industry_l or industry_l == "unknown"):
        return SecurityType.UNKNOWN

    return SecurityType.STANDARD


def evidence_from_stock_document(doc: Any) -> DividendRiskEvidence:
    """Map a StockDocument (or duck-typed equivalent) into assessment evidence."""
    payments = tuple(
        DividendPaymentEvidence(
            ex_date=record.ex_date,
            amount=float(record.amount),
            frequency=str(getattr(record, "frequency", "quarterly") or "quarterly"),
        )
        for record in (getattr(doc, "dividend_history", None) or [])
        if getattr(record, "ex_date", None) is not None
        and getattr(record, "amount", None) is not None
    )
    last_updated = getattr(doc, "last_updated", None)
    as_of: date | None
    if isinstance(last_updated, datetime):
        as_of = last_updated.date()
    elif isinstance(last_updated, date):
        as_of = last_updated
    else:
        as_of = None

    source = getattr(doc, "source", None)
    source_name = getattr(source, "value", None) or (str(source) if source else None)
    sources = (source_name,) if source_name else ()

    sector = getattr(doc, "sector", None)
    industry = getattr(doc, "industry", None)
    name = getattr(doc, "name", None)
    security_type = infer_security_type(sector=sector, industry=industry, name=name)

    cagr_3y = getattr(doc, "dividend_cagr_3y", None)
    if cagr_3y is None:
        # Prefer explicit 3y; fall back to stored 5y as growth-trend evidence.
        cagr_3y = getattr(doc, "dividend_cagr_5y", None)

    return DividendRiskEvidence(
        symbol=str(doc.symbol).upper(),
        security_type=security_type,
        sector=sector,
        industry=industry,
        name=name,
        annual_dividend=getattr(doc, "annual_dividend", None),
        earnings_payout_ratio=getattr(doc, "payout_ratio", None),
        fcf_payout_ratio=getattr(doc, "fcf_payout_ratio", None),
        dividend_coverage=getattr(doc, "dividend_coverage", None),
        dividend_cagr_3y=cagr_3y,
        dividend_payments=payments,
        data_as_of=as_of,
        source_names=sources,
    )


def evidence_from_stock_data(stock: Any) -> DividendRiskEvidence:
    """Map UI StockData into assessment evidence."""
    last_updated = getattr(stock, "_last_updated", None)
    as_of: date | None
    if isinstance(last_updated, datetime):
        as_of = last_updated.date()
    elif isinstance(last_updated, date):
        as_of = last_updated
    else:
        as_of = None

    dh = getattr(stock, "dividend_history", None)
    cagr = getattr(dh, "cagr_5y", None) if dh is not None else None
    sources = tuple(str(s) for s in (getattr(stock, "data_sources", None) or []) if s)
    sector = getattr(stock, "sector", None)
    industry = getattr(stock, "industry", None)
    name = getattr(stock, "name", None)

    return DividendRiskEvidence(
        symbol=str(stock.symbol).upper(),
        security_type=infer_security_type(sector=sector, industry=industry, name=name),
        sector=sector,
        industry=industry,
        name=name,
        annual_dividend=getattr(stock, "dividend_rate", None),
        earnings_payout_ratio=getattr(stock, "payout_ratio_pct", None),
        fcf_payout_ratio=getattr(stock, "fcf_payout_ratio_pct", None),
        dividend_coverage=getattr(stock, "dividend_coverage", None),
        dividend_cagr_3y=cagr,
        data_as_of=as_of,
        source_names=sources,
    )


def _is_special_frequency(frequency: str) -> bool:
    freq = frequency.strip().lower()
    return freq in {"special", "one-time", "onetime", "extra", "supplemental"}


def _regular_payments(
    payments: Sequence[DividendPaymentEvidence],
) -> list[DividendPaymentEvidence]:
    return sorted(
        (p for p in payments if not _is_special_frequency(p.frequency) and p.amount > 0),
        key=lambda p: p.ex_date,
    )


def _looks_like_split_adjustment(prior: float, current: float) -> bool:
    """Treat ~2:1 / 3:1 / 4:1 per-share drops as splits, not cuts."""
    if prior <= 0 or current <= 0 or current >= prior:
        return False
    ratio = prior / current
    for split in (2.0, 3.0, 4.0, 5.0, 10.0):
        if abs(ratio - split) / split <= SPLIT_RATIO_TOLERANCE:
            return True
    return False


def _detect_dividend_cut_signals(
    payments: Sequence[DividendPaymentEvidence],
    sources: tuple[str, ...],
) -> list[RiskSignal]:
    regular = _regular_payments(payments)
    if len(regular) < 2:
        return []

    # Compare last complete run-rate window vs prior window (payment count heuristic).
    recent_year = regular[-1].ex_date.year
    this_year = date.today().year
    by_year: dict[int, list[float]] = {}
    for payment in regular:
        by_year.setdefault(payment.ex_date.year, []).append(payment.amount)

    complete_years = sorted(year for year in by_year if year < recent_year or year < this_year)
    if len(complete_years) >= 2:
        y_prev, y_curr = complete_years[-2], complete_years[-1]
        # Prefer comparable annual totals when both years have payments.
        prior_total = sum(by_year[y_prev])
        curr_total = sum(by_year[y_curr])
        if prior_total > 0 and curr_total >= 0:
            if curr_total == 0:
                return [
                    RiskSignal(
                        code=SIGNAL_DIVIDEND_SUSPENSION,
                        severity="high",
                        message="Regular dividend appears suspended after a prior paying year.",
                        observed_value=0.0,
                        threshold_description="Any suspension of the regular dividend",
                        source_names=sources,
                    )
                ]
            # Normalize for payment-count differences using per-payment medians.
            prior_med = sorted(by_year[y_prev])[len(by_year[y_prev]) // 2]
            curr_med = sorted(by_year[y_curr])[len(by_year[y_curr]) // 2]
            if _looks_like_split_adjustment(prior_med, curr_med):
                return []
            change_pct = ((curr_med - prior_med) / prior_med) * 100.0
            if change_pct <= -DIVIDEND_CUT_MAJOR_PCT:
                return [
                    RiskSignal(
                        code=SIGNAL_DIVIDEND_CUT_MAJOR,
                        severity="high",
                        message=(
                            f"Regular dividend reduced by {abs(change_pct):.1f}% "
                            f"versus the prior year."
                        ),
                        observed_value=round(change_pct, 2),
                        threshold_description=(
                            f"Regular dividend reduced by {DIVIDEND_CUT_MAJOR_PCT:.0f}% or more"
                        ),
                        source_names=sources,
                    )
                ]
            if change_pct < 0:
                return [
                    RiskSignal(
                        code=SIGNAL_DIVIDEND_CUT_MINOR,
                        severity="monitor",
                        message=(
                            f"Regular dividend reduced by {abs(change_pct):.1f}% "
                            f"versus the prior year."
                        ),
                        observed_value=round(change_pct, 2),
                        threshold_description=(
                            f"Regular dividend reduced by less than {DIVIDEND_CUT_MAJOR_PCT:.0f}%"
                        ),
                        source_names=sources,
                    )
                ]

    # Fallback: consecutive regular per-share step-down.
    latest = regular[-1].amount
    prior = regular[-2].amount
    if _looks_like_split_adjustment(prior, latest):
        return []
    if prior > 0:
        change_pct = ((latest - prior) / prior) * 100.0
        if change_pct <= -DIVIDEND_CUT_MAJOR_PCT:
            return [
                RiskSignal(
                    code=SIGNAL_DIVIDEND_CUT_MAJOR,
                    severity="high",
                    message=(
                        f"Latest regular dividend is {abs(change_pct):.1f}% "
                        "below the prior payment."
                    ),
                    observed_value=round(change_pct, 2),
                    threshold_description=(
                        f"Regular dividend reduced by " f"{DIVIDEND_CUT_MAJOR_PCT:.0f}% or more"
                    ),
                    source_names=sources,
                )
            ]
        if change_pct < 0:
            return [
                RiskSignal(
                    code=SIGNAL_DIVIDEND_CUT_MINOR,
                    severity="monitor",
                    message=(
                        f"Latest regular dividend is {abs(change_pct):.1f}% "
                        "below the prior payment."
                    ),
                    observed_value=round(change_pct, 2),
                    threshold_description=(
                        f"Regular dividend reduced by less than " f"{DIVIDEND_CUT_MAJOR_PCT:.0f}%"
                    ),
                    source_names=sources,
                )
            ]
    return []


def _paying_dividend(evidence: DividendRiskEvidence) -> bool:
    if evidence.annual_dividend is not None and evidence.annual_dividend > 0:
        return True
    return any(
        not _is_special_frequency(p.frequency) and p.amount > 0 for p in evidence.dividend_payments
    )


def _core_fields_present(evidence: DividendRiskEvidence) -> bool:
    return any(
        (
            evidence.fcf_payout_ratio is not None,
            evidence.earnings_payout_ratio is not None,
            evidence.dividend_coverage is not None,
            len(_regular_payments(evidence.dividend_payments)) >= 2,
            evidence.affo_payout_ratio is not None,
            evidence.ffo_payout_ratio is not None,
            evidence.fcf_periods,
        )
    )


def _fcf_amount_signals(
    evidence: DividendRiskEvidence, *, paying: bool, sources: tuple[str, ...]
) -> list[RiskSignal]:
    if not paying:
        return []
    if evidence.fcf_zero_or_undefined:
        return [
            RiskSignal(
                code=SIGNAL_ZERO_DENOMINATOR,
                severity="high",
                message=(
                    "Free cash flow denominator is zero or undefined " "while dividends are paid."
                ),
                observed_value=0.0,
                threshold_description="FCF denominator must be positive to assess payout",
                source_names=sources,
            )
        ]
    if evidence.fcf_periods and evidence.fcf_periods[0] <= 0:
        return [
            RiskSignal(
                code=SIGNAL_FCF_NEGATIVE,
                severity="high",
                message="Free cash flow is zero or negative while dividends are paid.",
                observed_value=evidence.fcf_periods[0],
                threshold_description="Free cash flow <= 0 while dividends are paid",
                source_names=sources,
            )
        ]
    return []


def _fcf_payout_signals(
    fcf: float | None, *, paying: bool, sources: tuple[str, ...]
) -> list[RiskSignal]:
    if fcf is None:
        return []
    if fcf < 0 and paying:
        return [
            RiskSignal(
                code=SIGNAL_FCF_NEGATIVE,
                severity="high",
                message=(
                    "FCF payout is negative, indicating free cash flow "
                    "does not cover the dividend."
                ),
                observed_value=fcf,
                threshold_description="Free cash flow <= 0 while dividends are paid",
                source_names=sources,
            )
        ]
    if fcf > FCF_PAYOUT_HIGH_MIN_PCT:
        return [
            RiskSignal(
                code=SIGNAL_FCF_PAYOUT_CRITICAL,
                severity="high",
                message=f"FCF payout is {fcf:.1f}%.",
                observed_value=fcf,
                threshold_description=f"FCF payout above {FCF_PAYOUT_HIGH_MIN_PCT:.0f}%",
                source_names=sources,
            )
        ]
    if fcf >= FCF_PAYOUT_MONITOR_MIN_PCT:
        return [
            RiskSignal(
                code=SIGNAL_FCF_PAYOUT_ELEVATED,
                severity="monitor",
                message=f"FCF payout is {fcf:.1f}%.",
                observed_value=fcf,
                threshold_description=(
                    f"FCF payout from {FCF_PAYOUT_MONITOR_MIN_PCT:.0f}% "
                    f"to {FCF_PAYOUT_HIGH_MIN_PCT:.0f}%"
                ),
                source_names=sources,
            )
        ]
    return []


def _earnings_payout_signals(
    earn: float | None,
    coverage: float | None,
    *,
    paying: bool,
    sources: tuple[str, ...],
) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    if coverage is not None and coverage <= 0 and paying:
        signals.append(
            RiskSignal(
                code=SIGNAL_EARNINGS_NEGATIVE,
                severity="high",
                message=f"EPS coverage is {coverage:.2f}x while dividends are paid.",
                observed_value=coverage,
                threshold_description="EPS <= 0 while dividends are paid",
                source_names=sources,
            )
        )
    if earn is None:
        return signals
    if earn < 0 and paying:
        signals.append(
            RiskSignal(
                code=SIGNAL_EARNINGS_NEGATIVE,
                severity="high",
                message="Earnings payout is negative while dividends are paid.",
                observed_value=earn,
                threshold_description="EPS <= 0 while dividends are paid",
                source_names=sources,
            )
        )
    elif earn > EARNINGS_PAYOUT_HIGH_MIN_PCT:
        high = EARNINGS_PAYOUT_HIGH_MIN_PCT
        signals.append(
            RiskSignal(
                code=SIGNAL_EARNINGS_PAYOUT_CRITICAL,
                severity="high",
                message=f"Earnings payout is {earn:.1f}%.",
                observed_value=earn,
                threshold_description=f"Earnings payout above {high:.0f}%",
                source_names=sources,
            )
        )
    elif earn >= EARNINGS_PAYOUT_MONITOR_MIN_PCT:
        signals.append(
            RiskSignal(
                code=SIGNAL_EARNINGS_PAYOUT_ELEVATED,
                severity="monitor",
                message=f"Earnings payout is {earn:.1f}%.",
                observed_value=earn,
                threshold_description=(
                    f"Earnings payout from {EARNINGS_PAYOUT_MONITOR_MIN_PCT:.0f}% "
                    f"to {EARNINGS_PAYOUT_HIGH_MIN_PCT:.0f}%"
                ),
                source_names=sources,
            )
        )
    return signals


def _conflict_and_trend_signals(
    evidence: DividendRiskEvidence,
    *,
    fcf: float | None,
    earn: float | None,
    sources: tuple[str, ...],
) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    if fcf is not None and earn is not None:
        fcf_ok = fcf < FCF_PAYOUT_MONITOR_MIN_PCT
        earn_critical = earn > EARNINGS_PAYOUT_HIGH_MIN_PCT
        earn_ok = earn < EARNINGS_PAYOUT_MONITOR_MIN_PCT
        fcf_critical = fcf > FCF_PAYOUT_HIGH_MIN_PCT
        if (fcf_ok and earn_critical) or (earn_ok and fcf_critical):
            signals.append(
                RiskSignal(
                    code=SIGNAL_CONFLICTING_COVERAGE,
                    severity="info",
                    message=(
                        f"Coverage sources conflict (FCF payout {fcf:.1f}% vs "
                        f"earnings payout {earn:.1f}%). FCF evidence takes priority."
                    ),
                    observed_value=None,
                    threshold_description=("FCF evidence takes priority when both values exist"),
                    source_names=sources,
                )
            )

    if len(evidence.fcf_periods) >= 2:
        newest, prior = evidence.fcf_periods[0], evidence.fcf_periods[1]
        if newest < 0 and prior < 0:
            signals.append(
                RiskSignal(
                    code=SIGNAL_FCF_NEGATIVE_STREAK,
                    severity="high",
                    message=("Negative free cash flow in two consecutive " "comparable periods."),
                    observed_value=newest,
                    threshold_description=("Negative FCF in two consecutive comparable periods"),
                    source_names=sources,
                )
            )
        elif newest < prior:
            signals.append(
                RiskSignal(
                    code=SIGNAL_FCF_DECLINING,
                    severity="monitor",
                    message=("Free cash flow declined in two consecutive " "comparable periods."),
                    observed_value=newest,
                    threshold_description=("FCF declining in two consecutive comparable periods"),
                    source_names=sources,
                )
            )
    return signals


def _coverage_signals(evidence: DividendRiskEvidence) -> list[RiskSignal]:
    sources = evidence.source_names
    paying = _paying_dividend(evidence)
    fcf = evidence.fcf_payout_ratio
    earn = evidence.earnings_payout_ratio
    return [
        *_fcf_amount_signals(evidence, paying=paying, sources=sources),
        *_fcf_payout_signals(fcf, paying=paying, sources=sources),
        *_earnings_payout_signals(earn, evidence.dividend_coverage, paying=paying, sources=sources),
        *_conflict_and_trend_signals(evidence, fcf=fcf, earn=earn, sources=sources),
    ]


def _growth_signals(evidence: DividendRiskEvidence) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    cagr = evidence.dividend_cagr_3y
    if cagr is None:
        return signals
    if cagr < 0:
        signals.append(
            RiskSignal(
                code=SIGNAL_DIVIDEND_CAGR_NEGATIVE,
                severity="monitor",
                message=f"Dividend growth trend is negative ({cagr:.1f}% CAGR).",
                observed_value=cagr,
                threshold_description="Negative three-year dividend CAGR",
                source_names=evidence.source_names,
            )
        )
    elif cagr == 0:
        signals.append(
            RiskSignal(
                code=SIGNAL_DIVIDEND_NO_GROWTH,
                severity="monitor",
                message="No dividend growth across the observed three-year trend.",
                observed_value=0.0,
                threshold_description="No growth for three complete years",
                source_names=evidence.source_names,
            )
        )
    return signals


def _freshness_signals(
    evidence: DividendRiskEvidence,
    *,
    today: date,
) -> tuple[list[RiskSignal], ConfidenceLevel]:
    signals: list[RiskSignal] = []
    confidence = ConfidenceLevel.HIGH

    if evidence.data_as_of is None:
        signals.append(
            RiskSignal(
                code=SIGNAL_MISSING_AS_OF,
                severity="confidence",
                message="Data as-of date is missing; confidence is reduced.",
                threshold_description="Missing as-of date → low confidence",
                source_names=evidence.source_names,
            )
        )
        return signals, ConfidenceLevel.LOW

    age_days = (today - evidence.data_as_of).days
    if age_days > DATA_STALE_LOW_CONFIDENCE_DAYS:
        signals.append(
            RiskSignal(
                code=SIGNAL_DATA_STALE,
                severity="confidence",
                message=f"Evidence is {age_days} days old.",
                observed_value=float(age_days),
                threshold_description=(
                    f"Data older than {DATA_STALE_LOW_CONFIDENCE_DAYS} days → low confidence"
                ),
                source_names=evidence.source_names,
            )
        )
        confidence = ConfidenceLevel.LOW
    elif age_days > DATA_FRESHNESS_WARNING_DAYS:
        signals.append(
            RiskSignal(
                code=SIGNAL_DATA_FRESHNESS_WARNING,
                severity="confidence",
                message=f"Evidence is {age_days} days old.",
                observed_value=float(age_days),
                threshold_description=(
                    f"Data older than {DATA_FRESHNESS_WARNING_DAYS} days → freshness warning"
                ),
                source_names=evidence.source_names,
            )
        )
        confidence = ConfidenceLevel.MEDIUM

    return signals, confidence


def _missing_fields(evidence: DividendRiskEvidence) -> tuple[str, ...]:
    missing: list[str] = []
    if evidence.data_as_of is None:
        missing.append("data_as_of")
    if evidence.fcf_payout_ratio is None and not evidence.fcf_periods:
        missing.append("fcf_payout_ratio")
    if evidence.earnings_payout_ratio is None:
        missing.append("earnings_payout_ratio")
    if evidence.dividend_coverage is None:
        missing.append("dividend_coverage")
    if evidence.dividend_cagr_3y is None:
        missing.append("dividend_cagr_3y")
    if not evidence.dividend_payments:
        missing.append("dividend_payments")
    if evidence.security_type is SecurityType.REIT:
        if evidence.affo_payout_ratio is None:
            missing.append("affo_payout_ratio")
        if evidence.ffo_payout_ratio is None:
            missing.append("ffo_payout_ratio")
    return tuple(missing)


def _threshold_descriptions() -> dict[str, str]:
    return {
        "dividend_cut_major_pct": f"{DIVIDEND_CUT_MAJOR_PCT:.0f}%",
        "fcf_payout_monitor_min_pct": f"{FCF_PAYOUT_MONITOR_MIN_PCT:.0f}%",
        "fcf_payout_high_min_pct": f"{FCF_PAYOUT_HIGH_MIN_PCT:.0f}%",
        "earnings_payout_monitor_min_pct": f"{EARNINGS_PAYOUT_MONITOR_MIN_PCT:.0f}%",
        "earnings_payout_high_min_pct": f"{EARNINGS_PAYOUT_HIGH_MIN_PCT:.0f}%",
        "data_freshness_warning_days": str(DATA_FRESHNESS_WARNING_DAYS),
        "data_stale_low_confidence_days": str(DATA_STALE_LOW_CONFIDENCE_DAYS),
        "company_income_concentration_monitor_pct": (
            f"{COMPANY_INCOME_CONCENTRATION_MONITOR_PCT:.0f}%"
        ),
        "company_income_concentration_high_pct": (f"{COMPANY_INCOME_CONCENTRATION_HIGH_PCT:.0f}%"),
        "sector_income_concentration_monitor_pct": (
            f"{SECTOR_INCOME_CONCENTRATION_MONITOR_PCT:.0f}%"
        ),
        "sector_income_concentration_high_pct": f"{SECTOR_INCOME_CONCENTRATION_HIGH_PCT:.0f}%",
    }


def _has_fcf_evidence(evidence: DividendRiskEvidence, signals: Sequence[RiskSignal]) -> bool:
    if (
        evidence.fcf_payout_ratio is not None
        or evidence.fcf_periods
        or evidence.fcf_zero_or_undefined
    ):
        return True
    return any(s.code.startswith("FCF_") or s.code == SIGNAL_ZERO_DENOMINATOR for s in signals)


def _finalize_status(
    *,
    security_type: SecurityType,
    has_core: bool,
    signals: Sequence[RiskSignal],
    evidence: DividendRiskEvidence,
) -> RiskLevel:
    # 1. Unsupported security type / REIT without AFFO/FFO / ETF
    if security_type is SecurityType.ETF_FUND or security_type is SecurityType.UNKNOWN:
        return RiskLevel.SPECIAL_ANALYSIS_REQUIRED
    if security_type is SecurityType.REIT and (
        evidence.affo_payout_ratio is None and evidence.ffo_payout_ratio is None
    ):
        return RiskLevel.SPECIAL_ANALYSIS_REQUIRED

    # 2. Missing core evidence
    if not has_core:
        return RiskLevel.INSUFFICIENT_DATA

    codes = {s.code for s in signals}
    severities = {s.severity for s in signals}

    # Prefer FCF critical over earnings-only when both exist.
    fcf_priority = _has_fcf_evidence(evidence, signals)
    critical_fcf = {
        SIGNAL_FCF_NEGATIVE,
        SIGNAL_FCF_PAYOUT_CRITICAL,
        SIGNAL_FCF_NEGATIVE_STREAK,
        SIGNAL_ZERO_DENOMINATOR,
    }
    critical_earnings = {
        SIGNAL_EARNINGS_NEGATIVE,
        SIGNAL_EARNINGS_PAYOUT_CRITICAL,
    }
    cut_codes = {
        SIGNAL_DIVIDEND_CUT_MAJOR,
        SIGNAL_DIVIDEND_SUSPENSION,
    }

    # 3–5. Cuts / critical coverage
    if codes & cut_codes:
        return RiskLevel.HIGH_OBSERVED_RISK
    if codes & critical_fcf:
        return RiskLevel.HIGH_OBSERVED_RISK
    if (codes & critical_earnings) and not fcf_priority:
        return RiskLevel.HIGH_OBSERVED_RISK
    if (codes & critical_earnings) and fcf_priority:
        # FCF present: earnings critical still counts as high-risk evidence unless
        # FCF is clearly healthy (no FCF high/monitor/critical).
        fcf_stress = {
            SIGNAL_FCF_NEGATIVE,
            SIGNAL_FCF_PAYOUT_CRITICAL,
            SIGNAL_FCF_PAYOUT_ELEVATED,
            SIGNAL_FCF_NEGATIVE_STREAK,
            SIGNAL_FCF_DECLINING,
            SIGNAL_ZERO_DENOMINATOR,
        }
        if codes & fcf_stress:
            return RiskLevel.HIGH_OBSERVED_RISK
        # Healthy FCF with bad earnings → monitor (conflict), not automatic high.
        if SIGNAL_CONFLICTING_COVERAGE in codes:
            return RiskLevel.MONITOR
        return RiskLevel.HIGH_OBSERVED_RISK

    # 6–7. Monitoring signals (cash-flow deterioration / growth weakness)
    if "high" in severities:
        return RiskLevel.HIGH_OBSERVED_RISK
    if "monitor" in severities:
        return RiskLevel.MONITOR

    # 8. Freshness alone does not create monitor/high.
    return RiskLevel.LOWER_OBSERVED_RISK


def _summary_for(level: RiskLevel, signals: Sequence[RiskSignal]) -> str:
    actionable = [s for s in signals if s.severity in {"high", "monitor"}]
    if level is RiskLevel.SPECIAL_ANALYSIS_REQUIRED:
        return "This security type needs a specialized dividend-risk model."
    if level is RiskLevel.INSUFFICIENT_DATA:
        return "Not enough core evidence to assess dividend sustainability."
    if actionable:
        return actionable[0].message
    if level is RiskLevel.LOWER_OBSERVED_RISK:
        return "Available coverage and dividend-history evidence do not show elevated cut risk."
    return risk_level_label(level)


def assess_holding_dividend_risk(
    evidence: DividendRiskEvidence,
    *,
    today: date | None = None,
) -> HoldingDividendRiskAssessment:
    """Deterministic holding-level dividend sustainability assessment."""
    reference = today or date.today()
    sources = evidence.source_names
    signals: list[RiskSignal] = []

    security_type = evidence.security_type
    if security_type is SecurityType.UNKNOWN:
        security_type = infer_security_type(
            sector=evidence.sector,
            industry=evidence.industry,
            name=evidence.name,
        )

    # Rule 1 — unsupported / special types
    if security_type is SecurityType.ETF_FUND or security_type is SecurityType.UNKNOWN:
        signals.append(
            RiskSignal(
                code=SIGNAL_UNSUPPORTED_TYPE,
                severity="info",
                message=(
                    "Corporate earnings and free-cash-flow rules do not apply "
                    "to this security type."
                ),
                threshold_description="Unsupported model → special analysis required",
                source_names=sources,
            )
        )
        freshness, confidence = _freshness_signals(evidence, today=reference)
        signals.extend(freshness)
        level = RiskLevel.SPECIAL_ANALYSIS_REQUIRED
        return HoldingDividendRiskAssessment(
            symbol=evidence.symbol.upper(),
            risk_level=level,
            risk_label=risk_level_label(level),
            confidence=confidence,
            summary=_summary_for(level, signals),
            risk_signals=tuple(signals),
            observed_values={
                "security_type": security_type.value,
                "annual_dividend": evidence.annual_dividend,
            },
            threshold_descriptions=_threshold_descriptions(),
            missing_fields=_missing_fields(evidence),
            source_names=sources,
            data_as_of=evidence.data_as_of,
        )

    reit_missing_affo = (
        security_type is SecurityType.REIT
        and evidence.affo_payout_ratio is None
        and evidence.ffo_payout_ratio is None
    )
    if reit_missing_affo:
        signals.append(
            RiskSignal(
                code=SIGNAL_REIT_MISSING_AFFO_FFO,
                severity="info",
                message=(
                    "REIT assessment requires AFFO or FFO payout; " "EPS payout alone is not used."
                ),
                threshold_description="Without AFFO or FFO → special analysis required",
                source_names=sources,
            )
        )
        freshness, confidence = _freshness_signals(evidence, today=reference)
        signals.extend(freshness)
        level = RiskLevel.SPECIAL_ANALYSIS_REQUIRED
        return HoldingDividendRiskAssessment(
            symbol=evidence.symbol.upper(),
            risk_level=level,
            risk_label=risk_level_label(level),
            confidence=confidence,
            summary=_summary_for(level, signals),
            risk_signals=tuple(signals),
            observed_values={
                "security_type": security_type.value,
                "earnings_payout_ratio": evidence.earnings_payout_ratio,
            },
            threshold_descriptions=_threshold_descriptions(),
            missing_fields=_missing_fields(evidence),
            source_names=sources,
            data_as_of=evidence.data_as_of,
        )

    if security_type is SecurityType.REIT:
        # REIT with AFFO/FFO: evaluate using those payouts as FCF-equivalent.
        reit_evidence = DividendRiskEvidence(
            symbol=evidence.symbol,
            security_type=SecurityType.REIT,
            sector=evidence.sector,
            industry=evidence.industry,
            name=evidence.name,
            annual_dividend=evidence.annual_dividend,
            earnings_payout_ratio=None,  # do not use EPS payout for REITs
            fcf_payout_ratio=evidence.affo_payout_ratio or evidence.ffo_payout_ratio,
            dividend_coverage=None,
            fcf_periods=evidence.fcf_periods,
            affo_payout_ratio=evidence.affo_payout_ratio,
            ffo_payout_ratio=evidence.ffo_payout_ratio,
            dividend_cagr_3y=evidence.dividend_cagr_3y,
            dividend_payments=evidence.dividend_payments,
            data_as_of=evidence.data_as_of,
            source_names=sources,
        )
        evidence = reit_evidence

    has_core = _core_fields_present(evidence)
    if not has_core:
        signals.append(
            RiskSignal(
                code=SIGNAL_MISSING_CORE,
                severity="info",
                message="Core coverage or dividend-history evidence is missing.",
                threshold_description="Missing core evidence → insufficient data",
                source_names=sources,
            )
        )

    # Collect signals independently (order of append must not change final status).
    cut_signals = _detect_dividend_cut_signals(evidence.dividend_payments, sources)
    coverage_signals = _coverage_signals(evidence)
    growth_signals = _growth_signals(evidence)
    freshness_signals, confidence = _freshness_signals(evidence, today=reference)

    signals.extend(cut_signals)
    signals.extend(coverage_signals)
    signals.extend(growth_signals)
    signals.extend(freshness_signals)

    if security_type is SecurityType.BANK_INSURER:
        # Banks/insurers: keep payout/dividend evidence but lower confidence.
        confidence = (
            ConfidenceLevel.MEDIUM if confidence is ConfidenceLevel.HIGH else ConfidenceLevel.LOW
        )

    if (
        SIGNAL_CONFLICTING_COVERAGE in {s.code for s in signals}
        and confidence is ConfidenceLevel.HIGH
    ):
        confidence = ConfidenceLevel.MEDIUM

    level = _finalize_status(
        security_type=security_type,
        has_core=has_core,
        signals=signals,
        evidence=evidence,
    )

    # Missing data must never produce lower-risk.
    if level is RiskLevel.LOWER_OBSERVED_RISK and not has_core:
        level = RiskLevel.INSUFFICIENT_DATA

    observed: dict[str, Any] = {
        "security_type": security_type.value,
        "annual_dividend": evidence.annual_dividend,
        "fcf_payout_ratio": evidence.fcf_payout_ratio,
        "earnings_payout_ratio": evidence.earnings_payout_ratio,
        "dividend_coverage": evidence.dividend_coverage,
        "dividend_cagr_3y": evidence.dividend_cagr_3y,
        "affo_payout_ratio": evidence.affo_payout_ratio,
        "ffo_payout_ratio": evidence.ffo_payout_ratio,
        "fcf_periods": list(evidence.fcf_periods),
    }

    return HoldingDividendRiskAssessment(
        symbol=evidence.symbol.upper(),
        risk_level=level,
        risk_label=risk_level_label(level),
        confidence=confidence,
        summary=_summary_for(level, signals),
        risk_signals=tuple(signals),
        observed_values=observed,
        threshold_descriptions=_threshold_descriptions(),
        missing_fields=_missing_fields(evidence),
        source_names=sources,
        data_as_of=evidence.data_as_of,
    )


def assess_holdings_dividend_risk(
    evidence_by_symbol: Mapping[str, DividendRiskEvidence],
    *,
    today: date | None = None,
) -> dict[str, HoldingDividendRiskAssessment]:
    """Batch assess many holdings from preloaded evidence (one pass, no I/O)."""
    reference = today or date.today()
    return {
        symbol.upper(): assess_holding_dividend_risk(evidence, today=reference)
        for symbol, evidence in evidence_by_symbol.items()
    }


def _concentration_level(share_pct: float, *, monitor: float, high: float) -> ConcentrationLevel:
    if share_pct > high:
        return ConcentrationLevel.HIGH
    if share_pct >= monitor:
        return ConcentrationLevel.MONITOR
    return ConcentrationLevel.NONE


def assess_portfolio_dividend_income_risk(
    holdings: Sequence[PortfolioHoldingIncomeInput],
) -> PortfolioDividendIncomeRisk:
    """
    Portfolio income exposure by risk level + concentration.

    Concentration is separate from company sustainability status.
    Does not alter dividend forecasts.
    """
    income_by_level: dict[str, float] = {level.value: 0.0 for level in RiskLevel}
    total = 0.0
    sector_income: dict[str, float] = {}
    largest: tuple[str, float, float] | None = None

    for holding in holdings:
        income = max(0.0, float(holding.estimated_annual_income or 0.0))
        total += income
        level = (
            holding.assessment.risk_level.value
            if holding.assessment is not None
            else RiskLevel.INSUFFICIENT_DATA.value
        )
        income_by_level[level] = income_by_level.get(level, 0.0) + income
        sector = (holding.sector or "Unknown").strip() or "Unknown"
        sector_income[sector] = sector_income.get(sector, 0.0) + income

    elevated = sum(income_by_level.get(code, 0.0) for code in ELEVATED_RISK_LEVELS)

    if total > 0 and holdings:
        top = max(holdings, key=lambda h: max(0.0, float(h.estimated_annual_income or 0.0)))
        top_income = max(0.0, float(top.estimated_annual_income or 0.0))
        largest = (top.symbol.upper(), top_income, (top_income / total) * 100.0)

    largest_sector: tuple[str, float, float] | None = None
    if total > 0 and sector_income:
        sector_name, sector_amt = max(sector_income.items(), key=lambda item: item[1])
        # Ignore unreliable "Unknown"-only sector concentration for HIGH flags when
        # every row lacks sector — still report the bucket, but concentration stays NONE
        # unless a named sector reaches thresholds.
        share = (sector_amt / total) * 100.0
        largest_sector = (sector_name, sector_amt, share)

    company_conc = ConcentrationLevel.NONE
    if largest is not None:
        company_conc = _concentration_level(
            largest[2],
            monitor=COMPANY_INCOME_CONCENTRATION_MONITOR_PCT,
            high=COMPANY_INCOME_CONCENTRATION_HIGH_PCT,
        )

    sector_conc = ConcentrationLevel.NONE
    if largest_sector is not None and largest_sector[0] != "Unknown":
        sector_conc = _concentration_level(
            largest_sector[2],
            monitor=SECTOR_INCOME_CONCENTRATION_MONITOR_PCT,
            high=SECTOR_INCOME_CONCENTRATION_HIGH_PCT,
        )

    return PortfolioDividendIncomeRisk(
        total_estimated_annual_income=round(total, 2),
        income_by_risk_level={k: round(v, 2) for k, v in income_by_level.items()},
        income_elevated_risk=round(elevated, 2),
        largest_income_contributor=largest,
        largest_sector_income=largest_sector,
        company_concentration=company_conc,
        sector_concentration=sector_conc,
        holdings=tuple(holdings),
    )


def _holding_income_share(
    holding: PortfolioHoldingIncomeInput,
    total_income: float,
) -> float:
    if total_income <= 0:
        return 0.0
    return (max(0.0, float(holding.estimated_annual_income or 0.0)) / total_income) * 100.0


def _symbols_with_signal(
    holdings: Sequence[PortfolioHoldingIncomeInput],
    signal_code: str,
) -> list[str]:
    symbols: list[str] = []
    for holding in holdings:
        assessment = holding.assessment
        if assessment is None:
            continue
        if any(signal.code == signal_code for signal in assessment.risk_signals):
            symbols.append(holding.symbol.upper())
    return sorted(set(symbols))


def _signal_alert(
    holdings: Sequence[PortfolioHoldingIncomeInput],
    *,
    signal_code: str,
    alert_code: str,
    title: str,
    message_prefix: str,
    observed_value: float | None = None,
    alternate_signal: str | None = None,
) -> DividendRiskAlert | None:
    symbols = _symbols_with_signal(holdings, signal_code)
    if not symbols and alternate_signal:
        symbols = _symbols_with_signal(holdings, alternate_signal)
    if not symbols:
        return None
    return DividendRiskAlert(
        code=alert_code,
        severity="high",
        title=title,
        message=f"{message_prefix}{', '.join(symbols)}. Review evidence on the holding page.",
        symbols=tuple(symbols),
        observed_value=observed_value,
    )


def _concentration_alert(
    portfolio: PortfolioDividendIncomeRisk,
) -> DividendRiskAlert | None:
    if portfolio.company_concentration is not ConcentrationLevel.HIGH:
        return None
    if portfolio.largest_income_contributor is None:
        return None
    symbol, amount, share = portfolio.largest_income_contributor
    if share <= COMPANY_INCOME_CONCENTRATION_HIGH_PCT:
        return None
    return DividendRiskAlert(
        code=ALERT_COMPANY_INCOME_CONCENTRATION,
        severity="high",
        title="High company income concentration",
        message=(
            f"{symbol} contributes {share:.0f}% of estimated portfolio "
            f"dividend income (${amount:,.0f}). Concentration is separate "
            "from that company's sustainability status."
        ),
        symbols=(symbol,),
        observed_value=round(share, 1),
    )


def _insufficient_data_alert(
    holdings: Sequence[PortfolioHoldingIncomeInput],
    total: float,
) -> DividendRiskAlert | None:
    material_symbols: list[str] = []
    insufficient_income = 0.0
    all_insufficient: list[str] = []
    for holding in holdings:
        assessment = holding.assessment
        if assessment is None or assessment.risk_level is not RiskLevel.INSUFFICIENT_DATA:
            continue
        all_insufficient.append(holding.symbol.upper())
        income = max(0.0, float(holding.estimated_annual_income or 0.0))
        insufficient_income += income
        if _holding_income_share(holding, total) >= MATERIAL_INCOME_SHARE_PCT:
            material_symbols.append(holding.symbol.upper())
    insufficient_share = (insufficient_income / total * 100.0) if total > 0 else 0.0
    if not material_symbols and insufficient_share < MATERIAL_INCOME_SHARE_PCT:
        return None
    symbols = tuple(sorted(set(material_symbols))) or tuple(sorted(set(all_insufficient)))
    return DividendRiskAlert(
        code=ALERT_MATERIAL_INSUFFICIENT_DATA,
        severity="monitor",
        title="Material income without sufficient assessment data",
        message=(
            f"About {insufficient_share:.0f}% of estimated income "
            f"(${insufficient_income:,.0f}) lacks core evidence"
            + (f" — {', '.join(symbols)}" if symbols else "")
            + ". Missing data is never treated as lower risk."
        ),
        symbols=symbols,
        observed_value=round(insufficient_share, 1),
    )


def _stale_evidence_alert(
    holdings: Sequence[PortfolioHoldingIncomeInput],
    total: float,
) -> DividendRiskAlert | None:
    stale_symbols: list[str] = []
    stale_income = 0.0
    for holding in holdings:
        assessment = holding.assessment
        if assessment is None:
            continue
        codes = {signal.code for signal in assessment.risk_signals}
        if SIGNAL_DATA_STALE not in codes and SIGNAL_MISSING_AS_OF not in codes:
            continue
        if _holding_income_share(holding, total) < MATERIAL_INCOME_SHARE_PCT:
            continue
        stale_symbols.append(holding.symbol.upper())
        stale_income += max(0.0, float(holding.estimated_annual_income or 0.0))
    if not stale_symbols:
        return None
    stale_share = (stale_income / total * 100.0) if total > 0 else 0.0
    unique = tuple(sorted(set(stale_symbols)))
    return DividendRiskAlert(
        code=ALERT_MATERIAL_STALE_EVIDENCE,
        severity="monitor",
        title="Materially stale dividend evidence",
        message=(
            f"Evidence older than {DATA_STALE_LOW_CONFIDENCE_DAYS} days "
            f"(or missing as-of) for material income contributors: "
            + ", ".join(unique)
            + f" (~{stale_share:.0f}% of estimated income)."
        ),
        symbols=unique,
        observed_value=round(stale_share, 1),
    )


def build_high_value_dividend_risk_alerts(
    portfolio: PortfolioDividendIncomeRisk,
) -> tuple[DividendRiskAlert, ...]:
    """
    High-value portfolio alerts only (PR 4).

    Does not generate buy/sell/hold recommendations. Concentration stays separate
    from company sustainability status.
    """
    holdings = portfolio.holdings
    total = portfolio.total_estimated_annual_income
    alerts = [
        alert
        for alert in (
            _signal_alert(
                holdings,
                signal_code=SIGNAL_DIVIDEND_SUSPENSION,
                alert_code=ALERT_DIVIDEND_SUSPENSION,
                title="Dividend suspension observed",
                message_prefix="Regular dividend appears suspended for: ",
            ),
            _signal_alert(
                holdings,
                signal_code=SIGNAL_DIVIDEND_CUT_MAJOR,
                alert_code=ALERT_DIVIDEND_CUT_MAJOR,
                title="Meaningful dividend cut observed",
                message_prefix=(
                    f"Regular dividend reduced by {DIVIDEND_CUT_MAJOR_PCT:.0f}% " "or more for: "
                ),
                observed_value=DIVIDEND_CUT_MAJOR_PCT,
            ),
            _signal_alert(
                holdings,
                signal_code=SIGNAL_FCF_NEGATIVE,
                alert_code=ALERT_FCF_NEGATIVE,
                title="Negative free cash flow while paying dividends",
                message_prefix="Free cash flow does not support the dividend for: ",
                alternate_signal=SIGNAL_ZERO_DENOMINATOR,
            ),
            _concentration_alert(portfolio),
            _insufficient_data_alert(holdings, total),
            _stale_evidence_alert(holdings, total),
        )
        if alert is not None
    ]
    severity_rank = {"high": 0, "monitor": 1}
    alerts.sort(key=lambda alert: (severity_rank.get(alert.severity, 9), alert.code))
    return tuple(alerts)
