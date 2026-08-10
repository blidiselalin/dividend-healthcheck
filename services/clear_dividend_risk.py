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

METHODOLOGY_VERSION: Final[str] = "1.2"

# --- Threshold constants (single source; UI must import these) ---
# Coverage / cuts define sustainability. Absolute yield and leverage are soft
# context; Weiss yield-channel zones confirm yield traps (not automatic High).
DIVIDEND_CUT_MAJOR_PCT: Final[float] = 10.0
FCF_PAYOUT_MONITOR_MIN_PCT: Final[float] = 80.0
FCF_PAYOUT_HIGH_MIN_PCT: Final[float] = 100.0
EARNINGS_PAYOUT_MONITOR_MIN_PCT: Final[float] = 80.0
EARNINGS_PAYOUT_HIGH_MIN_PCT: Final[float] = 100.0
DEBT_TO_EBITDA_MONITOR_MIN: Final[float] = 5.0
DEBT_TO_EBITDA_HIGH_MIN: Final[float] = 8.0
INTEREST_COVERAGE_MONITOR_MAX: Final[float] = 2.0
INTEREST_COVERAGE_HIGH_MAX: Final[float] = 1.0
DIVIDEND_YIELD_STRETCH_PCT: Final[float] = 9.0
DIVIDEND_YIELD_EXTREME_PCT: Final[float] = 14.0
# Hard monitor signals required to escalate Monitor → High (soft signals excluded).
MULTI_MONITOR_HIGH_COUNT: Final[int] = 3
# Weiss channel: high historical-yield percentile can signal value — or a trap
# when coverage is already stressed.
YIELD_CHANNEL_TRAP_ZONES: Final[frozenset[str]] = frozenset({"Deep Value", "Value"})
YIELD_CHANNEL_RICH_ZONES: Final[frozenset[str]] = frozenset({"Caution", "Expensive"})
DATA_FRESHNESS_WARNING_DAYS: Final[int] = 120
DATA_STALE_LOW_CONFIDENCE_DAYS: Final[int] = 365
COMPANY_INCOME_CONCENTRATION_MONITOR_PCT: Final[float] = 25.0
COMPANY_INCOME_CONCENTRATION_HIGH_PCT: Final[float] = 40.0
SECTOR_INCOME_CONCENTRATION_MONITOR_PCT: Final[float] = 35.0
SECTOR_INCOME_CONCENTRATION_HIGH_PCT: Final[float] = 50.0
SPLIT_RATIO_TOLERANCE: Final[float] = 0.08
# Income share above which insufficient/stale evidence warrants a portfolio alert.
MATERIAL_INCOME_SHARE_PCT: Final[float] = 5.0

# Explicit classification when market docs lack sector/industry (adapter only).
KNOWN_REIT_SYMBOLS: Final[frozenset[str]] = frozenset({"O", "ARE", "AMT"})
KNOWN_STANDARD_SYMBOLS: Final[frozenset[str]] = frozenset(
    {"PEP", "HSY", "BTI", "BBY", "MO", "AWK", "BMY"}
)

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
SIGNAL_FCF_PAYOUT_CRITICAL = "FCF_PAYOUT_CRITICAL"
SIGNAL_FCF_PAYOUT_ELEVATED = "FCF_PAYOUT_ELEVATED"
SIGNAL_EARNINGS_NEGATIVE = "EPS_NEGATIVE_WHILE_PAYING"
SIGNAL_EARNINGS_PAYOUT_CRITICAL = "EARNINGS_PAYOUT_CRITICAL"
SIGNAL_EARNINGS_PAYOUT_ELEVATED = "EARNINGS_PAYOUT_ELEVATED"
SIGNAL_FCF_NEGATIVE_STREAK = "FCF_NEGATIVE_TWO_PERIODS"
SIGNAL_FCF_DECLINING = "FCF_DECLINING_TWO_PERIODS"
SIGNAL_DIVIDEND_CAGR_NEGATIVE = "DIVIDEND_CAGR_NEGATIVE"
SIGNAL_DIVIDEND_NO_GROWTH = "DIVIDEND_NO_GROWTH_THREE_YEARS"
SIGNAL_DEBT_TO_EBITDA_ELEVATED = "DEBT_TO_EBITDA_ELEVATED"
SIGNAL_DEBT_TO_EBITDA_HIGH = "DEBT_TO_EBITDA_HIGH"
SIGNAL_INTEREST_COVERAGE_WEAK = "INTEREST_COVERAGE_WEAK"
SIGNAL_INTEREST_COVERAGE_CRITICAL = "INTEREST_COVERAGE_CRITICAL"
SIGNAL_DIVIDEND_YIELD_STRETCHED = "DIVIDEND_YIELD_STRETCHED"
SIGNAL_DIVIDEND_YIELD_EXTREME = "DIVIDEND_YIELD_EXTREME"
SIGNAL_YIELD_CHANNEL_ZONE = "YIELD_CHANNEL_ZONE"
SIGNAL_YIELD_TRAP = "YIELD_TRAP"
SIGNAL_MULTI_MONITOR = "MULTI_MONITOR_ESCALATION"
SIGNAL_DATA_FRESHNESS_WARNING = "DATA_FRESHNESS_WARNING"
SIGNAL_DATA_STALE = "DATA_STALE_LOW_CONFIDENCE"
SIGNAL_MISSING_AS_OF = "MISSING_AS_OF_DATE"
SIGNAL_CONFLICTING_COVERAGE = "CONFLICTING_COVERAGE_SOURCES"
SIGNAL_ZERO_DENOMINATOR = "ZERO_DENOMINATOR_COVERAGE"

# Soft monitors inform the UI but do not escalate to High by themselves.
SOFT_MONITOR_CODES: Final[frozenset[str]] = frozenset(
    {
        SIGNAL_DEBT_TO_EBITDA_ELEVATED,
        SIGNAL_DEBT_TO_EBITDA_HIGH,
        SIGNAL_INTEREST_COVERAGE_WEAK,
        SIGNAL_INTEREST_COVERAGE_CRITICAL,
        SIGNAL_DIVIDEND_YIELD_STRETCHED,
        SIGNAL_DIVIDEND_YIELD_EXTREME,
        SIGNAL_DIVIDEND_CAGR_NEGATIVE,
        SIGNAL_DIVIDEND_NO_GROWTH,
        SIGNAL_FCF_DECLINING,
    }
)

HARD_MONITOR_CODES: Final[frozenset[str]] = frozenset(
    {
        SIGNAL_FCF_PAYOUT_ELEVATED,
        SIGNAL_EARNINGS_PAYOUT_ELEVATED,
        SIGNAL_DIVIDEND_CUT_MINOR,
    }
)

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
    dividend_yield: float | None = None
    earnings_payout_ratio: float | None = None
    fcf_payout_ratio: float | None = None
    dividend_coverage: float | None = None
    # Comparable-period free cash flow, newest first (optional series).
    fcf_periods: tuple[float, ...] = ()
    raw_free_cash_flow: float | None = None
    affo_payout_ratio: float | None = None
    ffo_payout_ratio: float | None = None
    dividend_cagr_3y: float | None = None
    debt_to_equity: float | None = None
    debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    dividend_payments: tuple[DividendPaymentEvidence, ...] = ()
    # Weiss yield-channel snapshot (optional; from preloaded YieldChannelData).
    yield_channel_zone: str | None = None
    yield_channel_percentile: float | None = None
    yield_channel_current: float | None = None
    yield_channel_median: float | None = None
    yield_channel_10th: float | None = None
    yield_channel_90th: float | None = None
    # Kept separate: fundamentals period vs document refresh vs history through.
    fundamentals_period_end: date | None = None
    document_updated_at: date | None = None
    dividend_history_through: date | None = None
    # Legacy alias used for freshness: prefer fundamentals, else document refresh.
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
    document_updated_at: date | None = None
    fundamentals_period_end: date | None = None
    dividend_history_through: date | None = None
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
    holdings_by_risk_level: dict[str, int]
    income_elevated_risk: float
    income_elevated_share_pct: float
    elevated_holdings_count: int
    high_risk_holdings_count: int
    monitor_holdings_count: int
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


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def infer_security_type(
    *,
    symbol: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    name: str | None = None,
    explicit: SecurityType | None = None,
) -> SecurityType:
    """Infer security type from classification text when quote type is absent."""
    if explicit is not None and explicit is not SecurityType.UNKNOWN:
        return explicit

    symbol_u = (symbol or "").strip().upper()
    if symbol_u in KNOWN_REIT_SYMBOLS:
        return SecurityType.REIT
    if symbol_u in KNOWN_STANDARD_SYMBOLS:
        return SecurityType.STANDARD

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
    if (
        "reit" in blob
        or industry_l.startswith("reit")
        or "real estate investment trust" in blob
        or sector_l == "real estate"
    ):
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
    document_updated_at = _coerce_date(getattr(doc, "last_updated", None))
    fundamentals_period_end = _coerce_date(
        getattr(doc, "fundamentals_period_end", None) or getattr(doc, "fundamentals_as_of", None)
    )
    history_through = max((p.ex_date for p in payments), default=None)
    # Freshness prefers fundamentals period; fall back to document refresh.
    data_as_of = fundamentals_period_end or document_updated_at

    source = getattr(doc, "source", None)
    source_name = getattr(source, "value", None) or (str(source) if source else None)
    sources = (source_name,) if source_name else ()

    symbol = str(getattr(doc, "symbol", "") or "").upper()
    sector = getattr(doc, "sector", None)
    industry = getattr(doc, "industry", None)
    name = getattr(doc, "name", None)
    security_type = infer_security_type(symbol=symbol, sector=sector, industry=industry, name=name)

    cagr_3y = getattr(doc, "dividend_cagr_3y", None)
    if cagr_3y is None:
        cagr_3y = getattr(doc, "dividend_cagr_5y", None)

    raw_fcf = getattr(doc, "free_cash_flow", None)
    if raw_fcf is None:
        raw_fcf = getattr(doc, "raw_free_cash_flow", None)
    fcf_zero = bool(raw_fcf is not None and raw_fcf <= 0)
    fcf_periods: tuple[float, ...] = ()
    if raw_fcf is not None:
        fcf_periods = (float(raw_fcf),)

    return DividendRiskEvidence(
        symbol=symbol,
        security_type=security_type,
        sector=sector,
        industry=industry,
        name=name,
        annual_dividend=getattr(doc, "annual_dividend", None),
        dividend_yield=getattr(doc, "dividend_yield", None),
        earnings_payout_ratio=getattr(doc, "payout_ratio", None),
        fcf_payout_ratio=getattr(doc, "fcf_payout_ratio", None),
        dividend_coverage=getattr(doc, "dividend_coverage", None),
        fcf_periods=fcf_periods,
        raw_free_cash_flow=float(raw_fcf) if raw_fcf is not None else None,
        affo_payout_ratio=getattr(doc, "affo_payout_ratio", None),
        ffo_payout_ratio=getattr(doc, "ffo_payout_ratio", None),
        dividend_cagr_3y=cagr_3y,
        debt_to_equity=getattr(doc, "debt_to_equity", None),
        debt_to_ebitda=getattr(doc, "debt_to_ebitda", None),
        interest_coverage=getattr(doc, "interest_coverage", None),
        dividend_payments=payments,
        fundamentals_period_end=fundamentals_period_end,
        document_updated_at=document_updated_at,
        dividend_history_through=history_through,
        data_as_of=data_as_of,
        source_names=sources,
        fcf_zero_or_undefined=fcf_zero,
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
    symbol = str(getattr(stock, "symbol", "") or "").upper()
    sector = getattr(stock, "sector", None)
    industry = getattr(stock, "industry", None)
    name = getattr(stock, "name", None)

    return DividendRiskEvidence(
        symbol=symbol,
        security_type=infer_security_type(
            symbol=symbol, sector=sector, industry=industry, name=name
        ),
        sector=sector,
        industry=industry,
        name=name,
        annual_dividend=getattr(stock, "dividend_rate", None),
        dividend_yield=getattr(stock, "dividend_yield_pct", None),
        earnings_payout_ratio=getattr(stock, "payout_ratio_pct", None),
        fcf_payout_ratio=getattr(stock, "fcf_payout_ratio_pct", None),
        dividend_coverage=getattr(stock, "dividend_coverage", None),
        debt_to_equity=getattr(stock, "debt_to_equity", None),
        debt_to_ebitda=getattr(stock, "debt_to_ebitda", None),
        interest_coverage=getattr(stock, "interest_coverage", None),
        dividend_cagr_3y=cagr,
        document_updated_at=as_of,
        data_as_of=as_of,
        source_names=sources,
    )


def with_yield_channel(evidence: DividendRiskEvidence, channel: Any | None) -> DividendRiskEvidence:
    """Attach a preloaded Weiss yield-channel snapshot (no I/O)."""
    if channel is None:
        return evidence
    from dataclasses import replace

    zone = getattr(channel, "zone", None)
    current = getattr(channel, "current_yield", None)
    return replace(
        evidence,
        dividend_yield=(float(current) if current is not None else evidence.dividend_yield),
        yield_channel_zone=str(zone) if zone else evidence.yield_channel_zone,
        yield_channel_percentile=_optional_float(getattr(channel, "percentile", None)),
        yield_channel_current=_optional_float(current),
        yield_channel_median=_optional_float(getattr(channel, "median_yield", None)),
        yield_channel_10th=_optional_float(getattr(channel, "yield_10th", None)),
        yield_channel_90th=_optional_float(getattr(channel, "yield_90th", None)),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _coverage_metric_count(evidence: DividendRiskEvidence) -> int:
    """Independent coverage metrics available for confidence / sufficiency."""
    count = 0
    if (
        evidence.fcf_payout_ratio is not None
        or evidence.fcf_periods
        or evidence.fcf_zero_or_undefined
        or evidence.raw_free_cash_flow is not None
    ):
        count += 1
    if evidence.earnings_payout_ratio is not None:
        count += 1
    if evidence.dividend_coverage is not None:
        count += 1
    if evidence.affo_payout_ratio is not None or evidence.ffo_payout_ratio is not None:
        count += 1
    return count


def _has_dividend_history(evidence: DividendRiskEvidence) -> bool:
    return len(_regular_payments(evidence.dividend_payments)) >= 2


def _core_fields_present(evidence: DividendRiskEvidence) -> bool:
    """Standard companies need at least one valid coverage metric to assess."""
    return _coverage_metric_count(evidence) >= 1


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


def _leverage_and_yield_signals(evidence: DividendRiskEvidence) -> list[RiskSignal]:
    """Soft balance-sheet / absolute-yield context — does not auto-escalate to High."""
    signals: list[RiskSignal] = []
    sources = evidence.source_names
    debt_ebitda = evidence.debt_to_ebitda
    if debt_ebitda is not None:
        if debt_ebitda >= DEBT_TO_EBITDA_HIGH_MIN:
            signals.append(
                RiskSignal(
                    code=SIGNAL_DEBT_TO_EBITDA_HIGH,
                    severity="monitor",
                    message=f"Debt / EBITDA is {debt_ebitda:.1f}x (elevated leverage).",
                    observed_value=debt_ebitda,
                    threshold_description=(
                        f"Debt / EBITDA at or above {DEBT_TO_EBITDA_HIGH_MIN:.0f}x"
                    ),
                    source_names=sources,
                )
            )
        elif debt_ebitda >= DEBT_TO_EBITDA_MONITOR_MIN:
            signals.append(
                RiskSignal(
                    code=SIGNAL_DEBT_TO_EBITDA_ELEVATED,
                    severity="monitor",
                    message=f"Debt / EBITDA is {debt_ebitda:.1f}x.",
                    observed_value=debt_ebitda,
                    threshold_description=(
                        f"Debt / EBITDA from {DEBT_TO_EBITDA_MONITOR_MIN:.0f}x "
                        f"to {DEBT_TO_EBITDA_HIGH_MIN:.0f}x"
                    ),
                    source_names=sources,
                )
            )

    coverage = evidence.interest_coverage
    if coverage is not None:
        if coverage < INTEREST_COVERAGE_HIGH_MAX:
            signals.append(
                RiskSignal(
                    code=SIGNAL_INTEREST_COVERAGE_CRITICAL,
                    severity="monitor",
                    message=f"Interest coverage is {coverage:.1f}x (thin).",
                    observed_value=coverage,
                    threshold_description=(
                        f"Interest coverage below {INTEREST_COVERAGE_HIGH_MAX:.1f}x"
                    ),
                    source_names=sources,
                )
            )
        elif coverage < INTEREST_COVERAGE_MONITOR_MAX:
            signals.append(
                RiskSignal(
                    code=SIGNAL_INTEREST_COVERAGE_WEAK,
                    severity="monitor",
                    message=f"Interest coverage is {coverage:.1f}x.",
                    observed_value=coverage,
                    threshold_description=(
                        f"Interest coverage below {INTEREST_COVERAGE_MONITOR_MAX:.0f}x"
                    ),
                    source_names=sources,
                )
            )

    # Absolute yield is soft context only — Weiss channel decides value vs trap.
    yield_pct = evidence.dividend_yield
    if yield_pct is not None and yield_pct > 0:
        if yield_pct >= DIVIDEND_YIELD_EXTREME_PCT:
            signals.append(
                RiskSignal(
                    code=SIGNAL_DIVIDEND_YIELD_EXTREME,
                    severity="monitor",
                    message=(
                        f"Absolute dividend yield is {yield_pct:.1f}% — "
                        "review coverage and yield-channel zone before treating as a trap."
                    ),
                    observed_value=yield_pct,
                    threshold_description=(
                        f"Dividend yield at or above {DIVIDEND_YIELD_EXTREME_PCT:.0f}%"
                    ),
                    source_names=sources,
                )
            )
        elif yield_pct >= DIVIDEND_YIELD_STRETCH_PCT:
            signals.append(
                RiskSignal(
                    code=SIGNAL_DIVIDEND_YIELD_STRETCHED,
                    severity="monitor",
                    message=(
                        f"Absolute dividend yield is {yield_pct:.1f}% — "
                        "context only until coverage confirms stress."
                    ),
                    observed_value=yield_pct,
                    threshold_description=(
                        f"Dividend yield from {DIVIDEND_YIELD_STRETCH_PCT:.0f}% "
                        f"to {DIVIDEND_YIELD_EXTREME_PCT:.0f}%"
                    ),
                    source_names=sources,
                )
            )
    return signals


def _coverage_stress_codes(signals: Sequence[RiskSignal]) -> set[str]:
    return {
        s.code
        for s in signals
        if s.code
        in {
            SIGNAL_FCF_NEGATIVE,
            SIGNAL_FCF_PAYOUT_CRITICAL,
            SIGNAL_FCF_PAYOUT_ELEVATED,
            SIGNAL_FCF_NEGATIVE_STREAK,
            SIGNAL_ZERO_DENOMINATOR,
            SIGNAL_EARNINGS_NEGATIVE,
            SIGNAL_EARNINGS_PAYOUT_CRITICAL,
            SIGNAL_EARNINGS_PAYOUT_ELEVATED,
            SIGNAL_DIVIDEND_CUT_MAJOR,
            SIGNAL_DIVIDEND_CUT_MINOR,
            SIGNAL_DIVIDEND_SUSPENSION,
        }
    }


def _yield_channel_signals(
    evidence: DividendRiskEvidence,
    *,
    prior_signals: Sequence[RiskSignal],
) -> list[RiskSignal]:
    """
    Weiss yield-channel context + yield-trap confirmation.

    High historical yield (Deep Value / Value) is an opportunity when coverage is
    healthy, and a trap only when coverage/cut evidence already shows stress.
    """
    signals: list[RiskSignal] = []
    sources = evidence.source_names
    zone = (evidence.yield_channel_zone or "").strip()
    if not zone:
        return signals

    percentile = evidence.yield_channel_percentile
    current = evidence.yield_channel_current
    median = evidence.yield_channel_median
    parts = [f"Yield channel zone: {zone}"]
    if current is not None and median is not None:
        parts.append(f"current {current:.1f}% vs median {median:.1f}%")
    elif current is not None:
        parts.append(f"current yield {current:.1f}%")
    if percentile is not None:
        parts.append(f"percentile {percentile:.0f}")

    if zone in YIELD_CHANNEL_TRAP_ZONES:
        message = (
            f"{'. '.join(parts)}. High yield vs history is a value signal unless "
            "coverage is already stressed."
        )
    elif zone in YIELD_CHANNEL_RICH_ZONES:
        message = (
            f"{'. '.join(parts)}. Low yield vs history suggests a rich price — "
            "not by itself a dividend-cut signal."
        )
    else:
        message = f"{'. '.join(parts)}."

    signals.append(
        RiskSignal(
            code=SIGNAL_YIELD_CHANNEL_ZONE,
            severity="info",
            message=message,
            observed_value=percentile,
            threshold_description="Weiss percentile bands on historical dividend yield",
            source_names=sources,
        )
    )

    stress = _coverage_stress_codes(prior_signals)
    trap_candidate = zone in YIELD_CHANNEL_TRAP_ZONES or (
        evidence.dividend_yield is not None
        and evidence.dividend_yield >= DIVIDEND_YIELD_EXTREME_PCT
    )
    if trap_candidate and stress:
        signals.append(
            RiskSignal(
                code=SIGNAL_YIELD_TRAP,
                severity="high",
                message=(
                    f"Possible yield trap: {zone or 'elevated absolute yield'} "
                    "coincides with stressed dividend coverage or a recent cut."
                ),
                observed_value=percentile if percentile is not None else evidence.dividend_yield,
                threshold_description=(
                    "Deep Value/Value channel (or extreme absolute yield) + coverage stress"
                ),
                source_names=sources,
            )
        )
    return signals


def _coverage_signals(evidence: DividendRiskEvidence) -> list[RiskSignal]:
    sources = evidence.source_names
    paying = _paying_dividend(evidence)
    fcf = evidence.fcf_payout_ratio
    earn = evidence.earnings_payout_ratio
    base = [
        *_fcf_amount_signals(evidence, paying=paying, sources=sources),
        *_fcf_payout_signals(fcf, paying=paying, sources=sources),
        *_earnings_payout_signals(earn, evidence.dividend_coverage, paying=paying, sources=sources),
        *_conflict_and_trend_signals(evidence, fcf=fcf, earn=earn, sources=sources),
        *_leverage_and_yield_signals(evidence),
    ]
    base.extend(_yield_channel_signals(evidence, prior_signals=base))
    return base


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
    if evidence.fundamentals_period_end is None:
        missing.append("fundamentals_period_end")
    if evidence.document_updated_at is None:
        missing.append("document_updated_at")
    if evidence.fcf_payout_ratio is None and evidence.raw_free_cash_flow is None:
        missing.append("fcf_payout_ratio")
    if evidence.raw_free_cash_flow is None:
        missing.append("raw_free_cash_flow")
    if evidence.earnings_payout_ratio is None:
        missing.append("earnings_payout_ratio")
    if evidence.dividend_coverage is None:
        missing.append("dividend_coverage")
    if evidence.dividend_cagr_3y is None:
        missing.append("dividend_cagr_3y")
    if not evidence.dividend_payments:
        missing.append("dividend_history")
    if evidence.security_type is SecurityType.REIT:
        if evidence.affo_payout_ratio is None:
            missing.append("affo_payout_ratio")
        if evidence.ffo_payout_ratio is None:
            missing.append("ffo_payout_ratio")
    if not evidence.source_names:
        missing.append("source_names")
    return tuple(missing)


def _threshold_descriptions() -> dict[str, str]:
    return {
        "dividend_cut_major_pct": f"{DIVIDEND_CUT_MAJOR_PCT:.0f}%",
        "fcf_payout_monitor_min_pct": f"{FCF_PAYOUT_MONITOR_MIN_PCT:.0f}%",
        "fcf_payout_high_min_pct": f"{FCF_PAYOUT_HIGH_MIN_PCT:.0f}%",
        "earnings_payout_monitor_min_pct": f"{EARNINGS_PAYOUT_MONITOR_MIN_PCT:.0f}%",
        "earnings_payout_high_min_pct": f"{EARNINGS_PAYOUT_HIGH_MIN_PCT:.0f}%",
        "debt_to_ebitda_monitor_min": f"{DEBT_TO_EBITDA_MONITOR_MIN:.0f}x",
        "debt_to_ebitda_high_min": f"{DEBT_TO_EBITDA_HIGH_MIN:.0f}x",
        "interest_coverage_monitor_max": f"{INTEREST_COVERAGE_MONITOR_MAX:.0f}x",
        "interest_coverage_high_max": f"{INTEREST_COVERAGE_HIGH_MAX:.1f}x",
        "dividend_yield_stretch_pct": f"{DIVIDEND_YIELD_STRETCH_PCT:.0f}%",
        "dividend_yield_extreme_pct": f"{DIVIDEND_YIELD_EXTREME_PCT:.0f}%",
        "multi_monitor_high_count": str(MULTI_MONITOR_HIGH_COUNT),
        "yield_channel_trap_zones": ", ".join(sorted(YIELD_CHANNEL_TRAP_ZONES)),
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

    # 6–7. High-severity sustainability / yield-trap signals
    if SIGNAL_YIELD_TRAP in codes:
        return RiskLevel.HIGH_OBSERVED_RISK
    hard_high = {
        s.code for s in signals if s.severity == "high" and s.code not in SOFT_MONITOR_CODES
    }
    if hard_high:
        return RiskLevel.HIGH_OBSERVED_RISK

    hard_monitor_count = sum(1 for s in signals if s.code in HARD_MONITOR_CODES)
    if hard_monitor_count >= MULTI_MONITOR_HIGH_COUNT:
        return RiskLevel.HIGH_OBSERVED_RISK

    # Soft monitors (leverage, absolute yield, mild growth) → Monitor at most.
    if "monitor" in severities:
        return RiskLevel.MONITOR

    # 8. Freshness / channel info alone does not create monitor/high.
    return RiskLevel.LOWER_OBSERVED_RISK


def _precise_insufficient_summary(evidence: DividendRiskEvidence) -> str:
    missing_cov: list[str] = []
    if evidence.fcf_payout_ratio is None and evidence.raw_free_cash_flow is None:
        missing_cov.append("free-cash-flow coverage")
    if evidence.earnings_payout_ratio is None and evidence.dividend_coverage is None:
        missing_cov.append("payout coverage")
    cov_text = " and ".join(missing_cov) if missing_cov else "coverage metrics"
    parts = [f"Unable to assess: {cov_text} are missing."]
    if evidence.dividend_history_through is not None:
        parts.append(
            "Dividend history is available through "
            f"{evidence.dividend_history_through.strftime('%B %Y')}."
        )
    elif _has_dividend_history(evidence):
        parts.append("Dividend history is available.")
    else:
        parts.append("Dividend history is missing.")
    if evidence.document_updated_at is not None:
        parts.append(
            "Market data was refreshed on " f"{evidence.document_updated_at.strftime('%B %d, %Y')}."
        )
    return " ".join(parts)


def _summary_for(
    level: RiskLevel,
    signals: Sequence[RiskSignal],
    *,
    evidence: DividendRiskEvidence | None = None,
) -> str:
    actionable = [s for s in signals if s.severity in {"high", "monitor"}]
    if level is RiskLevel.SPECIAL_ANALYSIS_REQUIRED:
        if any(s.code == SIGNAL_REIT_MISSING_AFFO_FFO for s in signals):
            return (
                "Special analysis required: AFFO or FFO payout data is unavailable. "
                "GAAP earnings payout is not used as the primary REIT coverage measure."
            )
        return "This security type needs a specialized dividend-risk model."
    if level is RiskLevel.INSUFFICIENT_DATA:
        if evidence is not None:
            return _precise_insufficient_summary(evidence)
        return "Not enough core evidence to assess dividend sustainability."
    if actionable:
        return actionable[0].message
    if level is RiskLevel.LOWER_OBSERVED_RISK:
        return "Available coverage and dividend-history evidence do not show elevated cut risk."
    return risk_level_label(level)


def _assessment_shell(
    evidence: DividendRiskEvidence,
    *,
    level: RiskLevel,
    confidence: ConfidenceLevel,
    signals: Sequence[RiskSignal],
    observed_values: dict[str, Any],
) -> HoldingDividendRiskAssessment:
    return HoldingDividendRiskAssessment(
        symbol=evidence.symbol.upper(),
        risk_level=level,
        risk_label=risk_level_label(level),
        confidence=confidence,
        summary=_summary_for(level, signals, evidence=evidence),
        risk_signals=tuple(signals),
        observed_values=observed_values,
        threshold_descriptions=_threshold_descriptions(),
        missing_fields=_missing_fields(evidence),
        source_names=evidence.source_names,
        data_as_of=evidence.data_as_of,
        document_updated_at=evidence.document_updated_at,
        fundamentals_period_end=evidence.fundamentals_period_end,
        dividend_history_through=evidence.dividend_history_through,
    )


def _apply_coverage_confidence(
    confidence: ConfidenceLevel,
    *,
    coverage_count: int,
) -> ConfidenceLevel:
    """One coverage metric → at most Medium; two+ can stay High when fresh."""
    if coverage_count <= 0:
        return ConfidenceLevel.LOW
    if coverage_count == 1:
        if confidence is ConfidenceLevel.HIGH:
            return ConfidenceLevel.MEDIUM
        return confidence
    return confidence


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
            symbol=evidence.symbol,
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
        return _assessment_shell(
            evidence,
            level=RiskLevel.SPECIAL_ANALYSIS_REQUIRED,
            confidence=confidence,
            signals=signals,
            observed_values={
                "security_type": security_type.value,
                "annual_dividend": evidence.annual_dividend,
            },
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
                    "REIT dividend coverage requires FFO or AFFO evidence. "
                    "GAAP earnings payout is not used as the primary REIT measure."
                ),
                threshold_description="Without AFFO or FFO → special analysis required",
                source_names=sources,
            )
        )
        freshness, confidence = _freshness_signals(evidence, today=reference)
        signals.extend(freshness)
        return _assessment_shell(
            evidence,
            level=RiskLevel.SPECIAL_ANALYSIS_REQUIRED,
            confidence=ConfidenceLevel.LOW,
            signals=signals,
            observed_values={
                "security_type": security_type.value,
                "earnings_payout_ratio": evidence.earnings_payout_ratio,
            },
        )

    if security_type is SecurityType.REIT:
        evidence = DividendRiskEvidence(
            symbol=evidence.symbol,
            security_type=SecurityType.REIT,
            sector=evidence.sector,
            industry=evidence.industry,
            name=evidence.name,
            annual_dividend=evidence.annual_dividend,
            dividend_yield=evidence.dividend_yield,
            earnings_payout_ratio=None,
            fcf_payout_ratio=evidence.affo_payout_ratio or evidence.ffo_payout_ratio,
            dividend_coverage=None,
            fcf_periods=evidence.fcf_periods,
            raw_free_cash_flow=evidence.raw_free_cash_flow,
            affo_payout_ratio=evidence.affo_payout_ratio,
            ffo_payout_ratio=evidence.ffo_payout_ratio,
            dividend_cagr_3y=evidence.dividend_cagr_3y,
            debt_to_equity=evidence.debt_to_equity,
            debt_to_ebitda=evidence.debt_to_ebitda,
            interest_coverage=evidence.interest_coverage,
            dividend_payments=evidence.dividend_payments,
            yield_channel_zone=evidence.yield_channel_zone,
            yield_channel_percentile=evidence.yield_channel_percentile,
            yield_channel_current=evidence.yield_channel_current,
            yield_channel_median=evidence.yield_channel_median,
            yield_channel_10th=evidence.yield_channel_10th,
            yield_channel_90th=evidence.yield_channel_90th,
            fundamentals_period_end=evidence.fundamentals_period_end,
            document_updated_at=evidence.document_updated_at,
            dividend_history_through=evidence.dividend_history_through,
            data_as_of=evidence.data_as_of,
            source_names=sources,
            fcf_zero_or_undefined=evidence.fcf_zero_or_undefined,
        )

    coverage_count = _coverage_metric_count(evidence)
    has_coverage = coverage_count >= 1
    cut_signals = _detect_dividend_cut_signals(evidence.dividend_payments, sources)
    has_cut_evidence = any(
        s.code in {SIGNAL_DIVIDEND_CUT_MAJOR, SIGNAL_DIVIDEND_SUSPENSION} for s in cut_signals
    )
    # Coverage required to assess; cuts may still elevate risk when incomplete.
    has_core = has_coverage or has_cut_evidence
    if not has_coverage and not has_cut_evidence:
        signals.append(
            RiskSignal(
                code=SIGNAL_MISSING_CORE,
                severity="info",
                message=_precise_insufficient_summary(evidence),
                threshold_description="No coverage metric → insufficient data",
                source_names=sources,
            )
        )

    coverage_signals = _coverage_signals(evidence)
    growth_signals = _growth_signals(evidence) if has_coverage else []
    freshness_signals, confidence = _freshness_signals(evidence, today=reference)

    signals.extend(cut_signals)
    signals.extend(coverage_signals)
    signals.extend(growth_signals)
    signals.extend(freshness_signals)

    confidence = _apply_coverage_confidence(confidence, coverage_count=coverage_count)

    if security_type is SecurityType.BANK_INSURER:
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

    if level is RiskLevel.LOWER_OBSERVED_RISK and not has_coverage:
        level = RiskLevel.INSUFFICIENT_DATA

    hard_monitor_count = sum(1 for s in signals if s.code in HARD_MONITOR_CODES)
    if (
        level is RiskLevel.HIGH_OBSERVED_RISK
        and hard_monitor_count >= MULTI_MONITOR_HIGH_COUNT
        and SIGNAL_YIELD_TRAP not in {s.code for s in signals}
        and not any(s.code == SIGNAL_MULTI_MONITOR for s in signals)
        and not any(
            s.severity == "high"
            and s.code
            in {
                SIGNAL_FCF_NEGATIVE,
                SIGNAL_FCF_PAYOUT_CRITICAL,
                SIGNAL_FCF_NEGATIVE_STREAK,
                SIGNAL_ZERO_DENOMINATOR,
                SIGNAL_EARNINGS_NEGATIVE,
                SIGNAL_EARNINGS_PAYOUT_CRITICAL,
                SIGNAL_DIVIDEND_CUT_MAJOR,
                SIGNAL_DIVIDEND_SUSPENSION,
            }
            for s in signals
        )
    ):
        signals.append(
            RiskSignal(
                code=SIGNAL_MULTI_MONITOR,
                severity="high",
                message=(
                    f"{hard_monitor_count} independent hard coverage/cut signals "
                    f"(threshold: {MULTI_MONITOR_HIGH_COUNT}+)."
                ),
                observed_value=float(hard_monitor_count),
                threshold_description=(
                    f"{MULTI_MONITOR_HIGH_COUNT}+ hard monitor signals → high observed risk"
                ),
                source_names=sources,
            )
        )

    observed: dict[str, Any] = {
        "security_type": security_type.value,
        "annual_dividend": evidence.annual_dividend,
        "dividend_yield": evidence.dividend_yield,
        "fcf_payout_ratio": evidence.fcf_payout_ratio,
        "earnings_payout_ratio": evidence.earnings_payout_ratio,
        "dividend_coverage": evidence.dividend_coverage,
        "raw_free_cash_flow": evidence.raw_free_cash_flow,
        "dividend_cagr_3y": evidence.dividend_cagr_3y,
        "debt_to_equity": evidence.debt_to_equity,
        "debt_to_ebitda": evidence.debt_to_ebitda,
        "interest_coverage": evidence.interest_coverage,
        "affo_payout_ratio": evidence.affo_payout_ratio,
        "ffo_payout_ratio": evidence.ffo_payout_ratio,
        "fcf_periods": list(evidence.fcf_periods),
        "coverage_metric_count": coverage_count,
        "hard_monitor_signal_count": hard_monitor_count,
        "yield_channel_zone": evidence.yield_channel_zone,
        "yield_channel_percentile": evidence.yield_channel_percentile,
        "yield_channel_current": evidence.yield_channel_current,
        "yield_channel_median": evidence.yield_channel_median,
        "fundamentals_period_end": evidence.fundamentals_period_end,
        "document_updated_at": evidence.document_updated_at,
        "dividend_history_through": evidence.dividend_history_through,
    }

    return _assessment_shell(
        evidence,
        level=level,
        confidence=confidence,
        signals=signals,
        observed_values=observed,
    )


def load_risk_evidence_batch(
    symbols: Sequence[str],
    *,
    documents: Mapping[str, Any] | None = None,
) -> dict[str, DividendRiskEvidence]:
    """Batch-load market documents and map to risk evidence (no UI rows)."""
    wanted = [str(symbol).upper() for symbol in symbols if symbol]
    docs: dict[str, Any] = dict(documents or {})
    missing = [symbol for symbol in wanted if symbol not in docs]
    if missing:
        from services.shared_market_db import load_documents

        docs.update(load_documents(missing))
    return {
        symbol: evidence_from_stock_document(docs[symbol]) for symbol in wanted if symbol in docs
    }


def assess_holdings_dividend_risk(
    evidence_by_symbol: Mapping[str, DividendRiskEvidence],
    *,
    today: date | None = None,
    yield_channels: Mapping[str, Any] | None = None,
) -> dict[str, HoldingDividendRiskAssessment]:
    """Batch assess many holdings from preloaded evidence (one pass, no I/O)."""
    reference = today or date.today()
    channels = yield_channels or {}
    out: dict[str, HoldingDividendRiskAssessment] = {}
    for symbol, evidence in evidence_by_symbol.items():
        key = symbol.upper()
        channel = channels.get(key) or channels.get(symbol)
        out[key] = assess_holding_dividend_risk(
            with_yield_channel(evidence, channel),
            today=reference,
        )
    return out


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
    holdings_by_level: dict[str, int] = {level.value: 0 for level in RiskLevel}
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
        holdings_by_level[level] = holdings_by_level.get(level, 0) + 1
        sector = (holding.sector or "Unknown").strip() or "Unknown"
        sector_income[sector] = sector_income.get(sector, 0.0) + income

    elevated = sum(income_by_level.get(code, 0.0) for code in ELEVATED_RISK_LEVELS)
    elevated_count = sum(holdings_by_level.get(code, 0) for code in ELEVATED_RISK_LEVELS)
    high_count = holdings_by_level.get(RiskLevel.HIGH_OBSERVED_RISK.value, 0)
    monitor_count = holdings_by_level.get(RiskLevel.MONITOR.value, 0)
    elevated_share = (elevated / total * 100.0) if total > 0 else 0.0

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
        holdings_by_risk_level=dict(holdings_by_level),
        income_elevated_risk=round(elevated, 2),
        income_elevated_share_pct=round(elevated_share, 1),
        elevated_holdings_count=elevated_count,
        high_risk_holdings_count=high_count,
        monitor_holdings_count=monitor_count,
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
