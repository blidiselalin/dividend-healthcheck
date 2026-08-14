"""
Session-only guest portfolio for the pre-login Command Center (no account required).

Users can explore a diversified sample list; holdings migrate to their account on sign-up.
Prices, yields, and risk come from the shared market library when a document exists.
Packaged snapshots are a fallback only — the demo does not invent live quotes.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from sqlite3 import Error as SQLiteError
from typing import Any, Literal

try:
    from psycopg import Error as PostgresError
except ImportError:
    PostgresError = type("PostgresError", (Exception,), {})

from data_ingestion.portfolio_store import PortfolioHolding

logger = logging.getLogger(__name__)

GUEST_SESSION_KEY = "guest_playground_holdings"
GUEST_SPOTLIGHT_KEY = "guest_playground_spotlight"
GUEST_MAX_HOLDINGS = 12
GUEST_INCOME_CONFIRM_KEY = "cc_demo_income_confirm"
GUEST_IMPORT_CONFIRM_KEY = "cc_demo_import_confirm"
GUEST_IMPORT_PREVIEW_KEY = "cc_demo_import_preview"

# Packaged fictitious sample — never accept arbitrary public uploads.
_DEMO_IBKR_SAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "demo" / "ibkr_activity_sample.csv"
)

DataMode = Literal["snapshot", "library", "snapshot+enrichment"]

# symbol, company, shares, avg_cost_usd — matches demo portfolio for a rich first paint
DEFAULT_GUEST_HOLDINGS: tuple[tuple[str, str, float, float], ...] = (
    ("KO", "Coca-Cola Co", 25.0, 58.0),
    ("JNJ", "Johnson & Johnson", 10.0, 155.0),
    ("MSFT", "Microsoft Corp", 4.0, 380.0),
    ("JPM", "JPMorgan Chase", 8.0, 195.0),
    ("HD", "Home Depot", 6.0, 350.0),
    ("O", "Realty Income Corp", 30.0, 52.0),
    ("VZ", "Verizon Communications", 40.0, 41.0),
    ("XOM", "Exxon Mobil", 12.0, 110.0),
    ("NEE", "NextEra Energy", 15.0, 70.0),
    ("CAT", "Caterpillar", 5.0, 320.0),
)

RISK_KIND_LOWER = "lower_observed_risk"
RISK_KIND_REIT = "reit_distribution"
RISK_KIND_YIELD_PAYOUT = "high_yield_payout"
RISK_KIND_CYCLICAL = "cyclical_cash_flow"
RISK_KIND_LEVERAGE = "leverage_coverage"
RISK_KIND_FCF = "fcf_stress"

DEMO_RISK_KIND_LABELS: dict[str, str] = {
    RISK_KIND_LOWER: "Lower observed risk",
    RISK_KIND_REIT: "REIT distribution coverage",
    RISK_KIND_YIELD_PAYOUT: "High yield + payout stress",
    RISK_KIND_CYCLICAL: "Cyclical cash flow",
    RISK_KIND_LEVERAGE: "Leverage / interest coverage",
    RISK_KIND_FCF: "Free-cash-flow coverage",
}

ELEVATED_DEMO_RISK_KINDS: frozenset[str] = frozenset(
    {
        RISK_KIND_REIT,
        RISK_KIND_YIELD_PAYOUT,
        RISK_KIND_CYCLICAL,
        RISK_KIND_LEVERAGE,
        RISK_KIND_FCF,
    }
)


@dataclass(frozen=True)
class DemoSymbolSnapshot:
    """Per-share demo metrics. Library overlays replace packaged fallbacks."""

    symbol: str
    company: str
    annual_dividend_per_share: float
    dividend_yield_pct: float
    payout_ratio_pct: float
    current_price: float
    next_pay_offset_days: int
    next_amount_per_share: float
    alert_severity: str
    alert_message: str
    sector: str = "Unknown"
    risk_kind: str = RISK_KIND_LOWER


# Packaged fallbacks when the market library has no document (no live API).
_DEMO_SNAPSHOTS: dict[str, DemoSymbolSnapshot] = {
    "KO": DemoSymbolSnapshot(
        symbol="KO",
        company="Coca-Cola Co",
        annual_dividend_per_share=1.94,
        dividend_yield_pct=3.1,
        payout_ratio_pct=72.0,
        current_price=62.5,
        next_pay_offset_days=18,
        next_amount_per_share=0.485,
        alert_severity="low",
        alert_message="Payout is moderate — sample review: confirm coverage vs peers.",
        sector="Consumer Staples",
        risk_kind=RISK_KIND_LOWER,
    ),
    "JNJ": DemoSymbolSnapshot(
        symbol="JNJ",
        company="Johnson & Johnson",
        annual_dividend_per_share=5.20,
        dividend_yield_pct=3.2,
        payout_ratio_pct=68.0,
        current_price=162.0,
        next_pay_offset_days=35,
        next_amount_per_share=1.30,
        alert_severity="low",
        alert_message="Sample signal: payout looks supported — still educational only.",
        sector="Health Care",
        risk_kind=RISK_KIND_LOWER,
    ),
    "MSFT": DemoSymbolSnapshot(
        symbol="MSFT",
        company="Microsoft Corp",
        annual_dividend_per_share=3.32,
        dividend_yield_pct=0.8,
        payout_ratio_pct=28.0,
        current_price=415.0,
        next_pay_offset_days=28,
        next_amount_per_share=0.83,
        alert_severity="low",
        alert_message="Low sample yield — growth-oriented name; income is secondary.",
        sector="Information Technology",
        risk_kind=RISK_KIND_LOWER,
    ),
    "JPM": DemoSymbolSnapshot(
        symbol="JPM",
        company="JPMorgan Chase",
        annual_dividend_per_share=5.05,
        dividend_yield_pct=2.5,
        payout_ratio_pct=30.0,
        current_price=202.0,
        next_pay_offset_days=20,
        next_amount_per_share=1.2625,
        alert_severity="low",
        alert_message="Sample payout looks supported — bank earnings still cycle with credit.",
        sector="Financials",
        risk_kind=RISK_KIND_LOWER,
    ),
    "HD": DemoSymbolSnapshot(
        symbol="HD",
        company="Home Depot",
        annual_dividend_per_share=9.00,
        dividend_yield_pct=2.4,
        payout_ratio_pct=55.0,
        current_price=375.0,
        next_pay_offset_days=16,
        next_amount_per_share=2.25,
        alert_severity="low",
        alert_message="Sample coverage looks measured — educational review aid only.",
        sector="Consumer Discretionary",
        risk_kind=RISK_KIND_LOWER,
    ),
    "O": DemoSymbolSnapshot(
        symbol="O",
        company="Realty Income Corp",
        annual_dividend_per_share=3.17,
        dividend_yield_pct=5.6,
        payout_ratio_pct=84.0,
        current_price=56.5,
        next_pay_offset_days=12,
        next_amount_per_share=0.264,
        alert_severity="medium",
        alert_message=(
            "REIT sample: payout ratio 84% — distributions leave less room if AFFO "
            "softens. Educational review aid only."
        ),
        sector="Real Estate",
        risk_kind=RISK_KIND_REIT,
    ),
    "VZ": DemoSymbolSnapshot(
        symbol="VZ",
        company="Verizon Communications",
        annual_dividend_per_share=2.71,
        dividend_yield_pct=6.4,
        payout_ratio_pct=88.0,
        current_price=42.0,
        next_pay_offset_days=22,
        next_amount_per_share=0.6775,
        alert_severity="high",
        alert_message=(
            "Sample yield 6.4% with elevated earnings payout — verify sustainability "
            "before treating income as durable. Educational only."
        ),
        sector="Communication Services",
        risk_kind=RISK_KIND_YIELD_PAYOUT,
    ),
    "XOM": DemoSymbolSnapshot(
        symbol="XOM",
        company="Exxon Mobil",
        annual_dividend_per_share=3.96,
        dividend_yield_pct=3.5,
        payout_ratio_pct=45.0,
        current_price=112.0,
        next_pay_offset_days=25,
        next_amount_per_share=0.99,
        alert_severity="medium",
        alert_message=(
            "Energy cash flows are cyclical in this sample — review coverage through the cycle."
        ),
        sector="Energy",
        risk_kind=RISK_KIND_CYCLICAL,
    ),
    "NEE": DemoSymbolSnapshot(
        symbol="NEE",
        company="NextEra Energy",
        annual_dividend_per_share=2.14,
        dividend_yield_pct=3.1,
        payout_ratio_pct=70.0,
        current_price=69.0,
        next_pay_offset_days=14,
        next_amount_per_share=0.535,
        alert_severity="medium",
        alert_message=(
            "Utility sample: leverage and rate sensitivity can pressure coverage even "
            "when the headline payout looks moderate. Educational only."
        ),
        sector="Utilities",
        risk_kind=RISK_KIND_LEVERAGE,
    ),
    "CAT": DemoSymbolSnapshot(
        symbol="CAT",
        company="Caterpillar",
        annual_dividend_per_share=5.64,
        dividend_yield_pct=1.7,
        payout_ratio_pct=48.0,
        current_price=332.0,
        next_pay_offset_days=32,
        next_amount_per_share=1.41,
        alert_severity="medium",
        alert_message=(
            "Industrial sample: free cash flow can compress late in the capex cycle "
            "while the dividend is still being paid. Educational only."
        ),
        sector="Industrials",
        risk_kind=RISK_KIND_FCF,
    ),
    "SCHD": DemoSymbolSnapshot(
        symbol="SCHD",
        company="Schwab US Dividend Equity ETF",
        annual_dividend_per_share=1.10,
        dividend_yield_pct=3.5,
        payout_ratio_pct=0.0,
        current_price=31.5,
        next_pay_offset_days=40,
        next_amount_per_share=0.275,
        alert_severity="low",
        alert_message="ETF sample — distributions vary; treat as illustrative only.",
        sector="ETF / Fund",
        risk_kind=RISK_KIND_LOWER,
    ),
    "PG": DemoSymbolSnapshot(
        symbol="PG",
        company="Procter & Gamble",
        annual_dividend_per_share=4.03,
        dividend_yield_pct=2.4,
        payout_ratio_pct=60.0,
        current_price=168.0,
        next_pay_offset_days=30,
        next_amount_per_share=1.0065,
        alert_severity="low",
        alert_message="Sample payout looks measured — educational review aid only.",
        sector="Consumer Staples",
        risk_kind=RISK_KIND_LOWER,
    ),
    "AAPL": DemoSymbolSnapshot(
        symbol="AAPL",
        company="Apple Inc",
        annual_dividend_per_share=1.00,
        dividend_yield_pct=0.5,
        payout_ratio_pct=15.0,
        current_price=210.0,
        next_pay_offset_days=45,
        next_amount_per_share=0.25,
        alert_severity="low",
        alert_message="Low sample yield — not an income-primary holding in this demo.",
        sector="Information Technology",
        risk_kind=RISK_KIND_LOWER,
    ),
}


@dataclass(frozen=True)
class GuestHolding:
    symbol: str
    shares: float
    avg_cost_per_share: float
    company_name: str = ""


@dataclass(frozen=True)
class GuestSafetyAlert:
    symbol: str
    company: str
    message: str
    severity: str  # high | medium | low
    suggested_check: str = "Compare payout, yield, and recent dividend history on Research."
    sector: str = ""
    risk_kind: str = RISK_KIND_LOWER


@dataclass(frozen=True)
class GuestNextPayout:
    symbol: str
    company: str
    pay_date: date | None
    amount_usd: float
    status: str


@dataclass
class GuestDashboard:
    holdings: list[GuestHolding] = field(default_factory=list)
    annual_income_usd: float = 0.0
    near_term_income_usd: float = 0.0
    monthly_forecast: list[tuple[str, float]] = field(default_factory=list)
    next_payouts: list[GuestNextPayout] = field(default_factory=list)
    safety_alerts: list[GuestSafetyAlert] = field(default_factory=list)
    rows: list[Any] = field(default_factory=list)
    library_ready: bool = False
    portfolio_value_usd: float = 0.0
    portfolio_yield_pct: float | None = None
    data_mode: DataMode = "snapshot"
    # Illustrative received-income example scaled to current holdings
    sample_received_gross_usd: float = 0.0
    sample_withholding_usd: float = 0.0
    sample_received_net_usd: float = 0.0
    provenance_label: str = "Illustrative snapshot · sample data only"


_LIBRARY_SNAPSHOTS: dict[str, DemoSymbolSnapshot] = {}


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def demo_snapshot_for(symbol: str) -> DemoSymbolSnapshot | None:
    key = _normalize_symbol(symbol)
    return _LIBRARY_SNAPSHOTS.get(key) or _DEMO_SNAPSHOTS.get(key)


def demo_risk_kind_label(kind: str) -> str:
    if kind in DEMO_RISK_KIND_LABELS:
        return DEMO_RISK_KIND_LABELS[kind]
    try:
        from services.clear_dividend_risk import RISK_LEVEL_LABELS
    except ImportError:
        return kind.replace("_", " ").title()
    for level, label in RISK_LEVEL_LABELS.items():
        if level.value == kind:
            return label
    return kind.replace("_", " ").title()


def demo_price_caption(dashboard: GuestDashboard) -> str:
    if dashboard.data_mode == "library":
        return "Market library"
    if dashboard.data_mode == "snapshot+enrichment":
        return "Library + snapshot fallback"
    return "Packaged snapshot"


def default_guest_holdings() -> list[GuestHolding]:
    return [
        GuestHolding(
            symbol=symbol,
            company_name=company,
            shares=shares,
            avg_cost_per_share=avg_cost,
        )
        for symbol, company, shares, avg_cost in DEFAULT_GUEST_HOLDINGS
    ]


def default_guest_symbols() -> tuple[str, ...]:
    return tuple(symbol for symbol, *_ in DEFAULT_GUEST_HOLDINGS)


def guest_holdings_from_session(session: Mapping[str, Any]) -> list[GuestHolding]:
    raw = session.get(GUEST_SESSION_KEY)
    if not raw:
        return default_guest_holdings()
    holdings: list[GuestHolding] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        symbol = _normalize_symbol(str(item.get("symbol", "")))
        if not symbol:
            continue
        holdings.append(
            GuestHolding(
                symbol=symbol,
                company_name=str(item.get("company_name") or item.get("company") or symbol),
                shares=float(item.get("shares") or 10.0),
                avg_cost_per_share=float(
                    item.get("avg_cost_per_share") or item.get("avg_cost") or 0.0
                ),
            )
        )
    return holdings[:GUEST_MAX_HOLDINGS] or default_guest_holdings()


def save_guest_holdings(session: dict[str, Any], holdings: Sequence[GuestHolding]) -> None:
    session[GUEST_SESSION_KEY] = [
        {
            "symbol": h.symbol,
            "company_name": h.company_name,
            "shares": h.shares,
            "avg_cost_per_share": h.avg_cost_per_share,
        }
        for h in holdings[:GUEST_MAX_HOLDINGS]
    ]


def add_guest_holding(
    session: dict[str, Any],
    *,
    symbol: str,
    shares: float = 10.0,
    avg_cost_per_share: float | None = None,
    company_name: str | None = None,
) -> tuple[list[GuestHolding], str | None]:
    """Add or update a guest holding. Returns (holdings, error_message).

    When updating an existing symbol, omitted cost/name preserve prior metadata.
    """
    symbol = _normalize_symbol(symbol)
    if not symbol:
        return guest_holdings_from_session(session), "Enter a ticker symbol."

    current = guest_holdings_from_session(session)
    existing = next((h for h in current if h.symbol == symbol), None)
    if existing is None and len(current) >= GUEST_MAX_HOLDINGS:
        return (
            current,
            f"Try up to {GUEST_MAX_HOLDINGS} stocks before sign-up — remove one to add another.",
        )

    snap = demo_snapshot_for(symbol)
    if existing is not None:
        cost = (
            existing.avg_cost_per_share
            if avg_cost_per_share is None
            else max(0.0, float(avg_cost_per_share))
        )
        name = existing.company_name
        if company_name is not None and str(company_name).strip():
            name = str(company_name).strip()
    else:
        cost = (
            float(snap.current_price)
            if avg_cost_per_share is None and snap is not None
            else (0.0 if avg_cost_per_share is None else max(0.0, float(avg_cost_per_share)))
        )
        name = (
            (str(company_name).strip() if company_name else "")
            or (snap.company if snap else "")
            or symbol
        )

    updated = [h for h in current if h.symbol != symbol]
    updated.append(
        GuestHolding(
            symbol=symbol,
            shares=max(0.0, float(shares)),
            avg_cost_per_share=cost,
            company_name=name,
        )
    )
    updated.sort(key=lambda h: h.symbol)
    save_guest_holdings(session, updated)
    session[GUEST_SPOTLIGHT_KEY] = symbol
    return updated, None


def remove_guest_holding(
    session: dict[str, Any], symbol: str
) -> tuple[list[GuestHolding], str | None]:
    """Remove a guest holding. The last sample holding cannot be removed."""
    symbol = _normalize_symbol(symbol)
    current = guest_holdings_from_session(session)
    if len(current) <= 1:
        return (
            current,
            "Keep at least one sample holding so the demo can show income and risk.",
        )
    updated = [h for h in current if h.symbol != symbol]
    if not updated:
        return (
            current,
            "Keep at least one sample holding so the demo can show income and risk.",
        )
    save_guest_holdings(session, updated)
    return updated, None


def replace_guest_holdings_from_positions(
    session: dict[str, Any],
    positions: Sequence[tuple[str, float, float, str]],
) -> list[GuestHolding]:
    """Replace guest holdings from (symbol, shares, avg_cost, company) tuples — session only."""
    holdings: list[GuestHolding] = []
    for symbol, shares, avg_cost, company in positions[:GUEST_MAX_HOLDINGS]:
        symbol_u = _normalize_symbol(symbol)
        if not symbol_u or shares <= 0:
            continue
        snap = demo_snapshot_for(symbol_u)
        holdings.append(
            GuestHolding(
                symbol=symbol_u,
                shares=float(shares),
                avg_cost_per_share=float(avg_cost)
                if avg_cost > 0
                else (snap.current_price if snap else 0.0),
                company_name=(company or (snap.company if snap else "") or symbol_u),
            )
        )
    if not holdings:
        holdings = default_guest_holdings()
    save_guest_holdings(session, holdings)
    if holdings:
        session[GUEST_SPOTLIGHT_KEY] = holdings[0].symbol
    return holdings


@dataclass(frozen=True)
class GuestImportPreview:
    """Read-only preview of the packaged sample IBKR statement."""

    path: str
    open_positions: int
    trades: int
    dividends: int
    withholdings: int
    deposits: int
    warnings: int
    position_rows: tuple[tuple[str, float, float, str], ...]


def load_packaged_ibkr_sample_preview(
    path: Path | None = None,
) -> GuestImportPreview:
    """Parse the packaged fictitious IBKR CSV — no uploads, no DB writes."""
    sample_path = path or _DEMO_IBKR_SAMPLE_PATH
    content = sample_path.read_text(encoding="utf-8")
    from services.ibkr_activity_parser import parse_activity_statement_csv

    statement = parse_activity_statement_csv(content)
    from services.ibkr_activity_parser import ImportIssueLevel

    warning_count = sum(
        1
        for issue in getattr(statement, "issues", [])
        if getattr(issue, "level", None) == ImportIssueLevel.WARNING
    )
    positions: list[tuple[str, float, float, str]] = []
    for pos in statement.open_positions[:GUEST_MAX_HOLDINGS]:
        snap = demo_snapshot_for(pos.symbol)
        positions.append(
            (
                pos.symbol,
                float(pos.shares),
                float(pos.cost_price or 0.0),
                snap.company if snap else pos.symbol,
            )
        )
    deposits = len(
        [row for row in statement.cash_transfers if float(getattr(row, "amount", 0) or 0) > 0]
    )
    return GuestImportPreview(
        path=str(sample_path),
        open_positions=len(statement.open_positions),
        trades=len(statement.trades),
        dividends=len(statement.dividends),
        withholdings=len(statement.withholdings),
        deposits=deposits,
        warnings=warning_count,
        position_rows=tuple(positions),
    )


def apply_packaged_ibkr_sample_to_guest(
    session: dict[str, Any],
    *,
    path: Path | None = None,
) -> tuple[list[GuestHolding], GuestImportPreview]:
    """Replace guest holdings from the packaged sample — session only."""
    preview = load_packaged_ibkr_sample_preview(path=path)
    holdings = replace_guest_holdings_from_positions(session, preview.position_rows)
    session[GUEST_IMPORT_PREVIEW_KEY] = {
        "open_positions": preview.open_positions,
        "trades": preview.trades,
        "dividends": preview.dividends,
        "withholdings": preview.withholdings,
        "deposits": preview.deposits,
        "warnings": preview.warnings,
    }
    session[GUEST_IMPORT_CONFIRM_KEY] = {
        "symbols": [h.symbol for h in holdings],
        "holding_count": len(holdings),
        "open_positions": preview.open_positions,
        "trades": preview.trades,
        "dividends": preview.dividends,
    }
    for holding in holdings:
        session[f"cc_demo_shares_{holding.symbol}"] = float(holding.shares)
    return holdings, preview


def to_portfolio_holdings(guest: Sequence[GuestHolding]) -> list[PortfolioHolding]:
    rows: list[PortfolioHolding] = []
    for index, item in enumerate(guest):
        acquisition = item.shares * item.avg_cost_per_share
        rows.append(
            PortfolioHolding(
                symbol=item.symbol,
                shares=item.shares,
                avg_cost_per_share=item.avg_cost_per_share,
                acquisition_value=acquisition,
                commission=0.0,
                dividends_paid=0.0,
                estimated_avg_price=item.avg_cost_per_share,
                sort_order=index,
                company_name=item.company_name or None,
            )
        )
    return rows


def estimate_annual_income_usd(guest: Sequence[GuestHolding]) -> float:
    """Snapshot-based annual income — available without the market library."""
    total = 0.0
    for holding in guest:
        snap = demo_snapshot_for(holding.symbol)
        if snap is None:
            continue
        total += holding.shares * snap.annual_dividend_per_share
    return round(total, 2)


def _month_labels(start: date, count: int = 12) -> list[str]:
    labels: list[str] = []
    year, month = start.year, start.month
    for _ in range(count):
        labels.append(date(year, month, 1).strftime("%b %Y"))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return labels


def _build_snapshot_dashboard(guest: Sequence[GuestHolding]) -> GuestDashboard:
    today = date.today()
    holdings = list(guest)
    annual = 0.0
    near_term = 0.0
    value = 0.0
    payouts: list[GuestNextPayout] = []
    alerts: list[GuestSafetyAlert] = []
    rows: list[Any] = []

    for holding in holdings:
        snap = demo_snapshot_for(holding.symbol)
        if snap is None:
            # Unsupported symbol: keep holding but contribute zero income.
            value += holding.shares * holding.avg_cost_per_share
            continue
        income = holding.shares * snap.annual_dividend_per_share
        annual += income
        price = snap.current_price or holding.avg_cost_per_share
        value += holding.shares * price
        pay_date = today + timedelta(days=snap.next_pay_offset_days)
        next_cash = holding.shares * snap.next_amount_per_share
        near_term += next_cash
        payouts.append(
            GuestNextPayout(
                symbol=holding.symbol,
                company=holding.company_name or snap.company,
                pay_date=pay_date,
                amount_usd=round(next_cash, 2),
                status="Estimated",
            )
        )
        if snap.alert_severity in {"high", "medium"} or snap.risk_kind in ELEVATED_DEMO_RISK_KINDS:
            kind_label = DEMO_RISK_KIND_LABELS.get(snap.risk_kind, snap.risk_kind)
            alerts.append(
                GuestSafetyAlert(
                    symbol=holding.symbol,
                    company=holding.company_name or snap.company,
                    message=snap.alert_message,
                    severity=snap.alert_severity,
                    suggested_check=(
                        f"Open Research for {holding.symbol} and compare {kind_label.lower()}, "
                        "payout, yield, and dividend history."
                    ),
                    sector=snap.sector,
                    risk_kind=snap.risk_kind,
                )
            )
        rows.append(
            type(
                "SnapshotRow",
                (),
                {
                    "ticker": holding.symbol,
                    "company": holding.company_name or snap.company,
                    "shares": holding.shares,
                    "current_value": round(holding.shares * price, 2),
                    "annual_income": round(income, 2),
                    "dividend_yield_pct": snap.dividend_yield_pct,
                    "payout_ratio_pct": snap.payout_ratio_pct,
                    "profit_pct": (
                        round((price / holding.avg_cost_per_share - 1) * 100, 1)
                        if holding.avg_cost_per_share > 0
                        else None
                    ),
                },
            )()
        )

    payouts.sort(key=lambda p: (p.pay_date or date.max, -p.amount_usd))
    alerts.sort(key=lambda a: {"high": 0, "medium": 1, "low": 2}.get(a.severity, 9))

    # Spread annual income across 12 months with a mild seasonal pattern.
    labels = _month_labels(today.replace(day=1))
    weights = [0.9, 0.85, 1.1, 0.95, 0.9, 1.15, 0.95, 0.9, 1.1, 0.95, 0.9, 1.35]
    weight_sum = sum(weights)
    monthly = [
        (label, round(annual * (weight / weight_sum), 2)) for label, weight in zip(labels, weights)
    ]

    # Illustrative received cash ≈ one quarter of annual, with 15% withholding.
    sample_gross = round(annual * 0.25, 2) if annual else 0.0
    sample_tax = round(sample_gross * 0.15, 2)
    sample_net = round(sample_gross - sample_tax, 2)

    dashboard = GuestDashboard(
        holdings=holdings,
        annual_income_usd=round(annual, 2),
        near_term_income_usd=round(near_term, 2),
        monthly_forecast=monthly,
        next_payouts=payouts[:12],
        safety_alerts=alerts[:10],
        rows=rows,
        library_ready=False,
        data_mode="snapshot",
        sample_received_gross_usd=sample_gross,
        sample_withholding_usd=sample_tax,
        sample_received_net_usd=sample_net,
        provenance_label="Illustrative snapshot · sample data only · not live market quotes",
    )
    _apply_portfolio_metrics(dashboard)
    if dashboard.portfolio_value_usd <= 0:
        dashboard.portfolio_value_usd = round(value, 2)
        if value > 0 and annual:
            dashboard.portfolio_yield_pct = round(annual / value * 100, 2)
    return dashboard


def _yield_pct(price: float, dps: float | None, raw_yield: float | None) -> float:
    if raw_yield is not None and raw_yield > 1:
        return float(raw_yield)
    if price > 0 and dps:
        return round(dps / price * 100, 2)
    if raw_yield is not None and raw_yield <= 1:
        return round(float(raw_yield) * 100, 2)
    return 0.0


def _next_pay_from_document(doc: Any, *, dps: float, today: date) -> tuple[int, float]:
    freq = int(getattr(doc, "payment_frequency", None) or 4) or 4
    next_amt = dps / freq if dps > 0 else 0.0
    ex = getattr(doc, "ex_dividend_date", None)
    if isinstance(ex, datetime):
        ex = ex.date()
    if isinstance(ex, date):
        delta = (ex - today).days
        if delta >= 0:
            return delta, next_amt
        return min(90, abs(delta) or 30), next_amt
    return 30, next_amt


def _risk_from_document(doc: Any) -> tuple[str, str, str]:
    """Return (severity, message, risk_kind) from Clear Dividend Risk."""
    from services.clear_dividend_risk import (
        RiskLevel,
        assess_holding_dividend_risk,
        evidence_from_stock_document,
    )

    assessment = assess_holding_dividend_risk(evidence_from_stock_document(doc))
    level = assessment.risk_level
    if level is RiskLevel.HIGH_OBSERVED_RISK:
        severity = "high"
    elif level in {
        RiskLevel.MONITOR,
        RiskLevel.SPECIAL_ANALYSIS_REQUIRED,
        RiskLevel.INSUFFICIENT_DATA,
    }:
        severity = "medium"
    else:
        severity = "low"
    message = assessment.summary or assessment.risk_label
    for signal in assessment.risk_signals:
        if signal.severity in {"high", "monitor"} and signal.message:
            message = signal.message
            break
    return severity, message, level.value


def _snapshot_from_library_document(doc: Any) -> DemoSymbolSnapshot | None:
    symbol = _normalize_symbol(str(getattr(doc, "symbol", "") or ""))
    if not symbol:
        return None
    raw_price = getattr(doc, "current_price", None)
    if raw_price is None:
        return None
    price = float(raw_price)
    if price <= 0:
        return None
    raw_dps = getattr(doc, "annual_dividend", None)
    raw_yield = getattr(doc, "dividend_yield", None)
    dps = float(raw_dps) if raw_dps is not None else None
    if dps is None and raw_yield is not None and price > 0:
        yld = float(raw_yield)
        dps = price * (yld if yld <= 1 else yld / 100.0)
    if dps is None or dps < 0:
        return None
    yld_pct = _yield_pct(price, dps, float(raw_yield) if raw_yield is not None else None)
    raw_payout = getattr(doc, "payout_ratio", None)
    payout = float(raw_payout) if raw_payout is not None else 0.0
    company = str(getattr(doc, "name", "") or symbol)
    sector = str(getattr(doc, "sector", "") or "Unknown")
    offset, next_amt = _next_pay_from_document(doc, dps=dps, today=date.today())
    try:
        severity, message, risk_kind = _risk_from_document(doc)
    except (TypeError, ValueError, AttributeError, KeyError):
        packaged = _DEMO_SNAPSHOTS.get(symbol)
        if packaged is not None:
            severity, message, risk_kind = (
                packaged.alert_severity,
                packaged.alert_message,
                packaged.risk_kind,
            )
        else:
            severity, message, risk_kind = (
                "low",
                "Market library holding — risk evidence incomplete.",
                RISK_KIND_LOWER,
            )
    return DemoSymbolSnapshot(
        symbol=symbol,
        company=company,
        annual_dividend_per_share=round(dps, 4),
        dividend_yield_pct=yld_pct,
        payout_ratio_pct=payout,
        current_price=round(price, 4),
        next_pay_offset_days=offset,
        next_amount_per_share=round(next_amt, 4),
        alert_severity=severity,
        alert_message=message,
        sector=sector,
        risk_kind=risk_kind,
    )


def _try_enrich_from_library(dashboard: GuestDashboard, guest: Sequence[GuestHolding]) -> None:
    """Overlay shared-library documents. Never calls live Yahoo."""
    from services.shared_market_db import load_documents

    docs = load_documents([h.symbol for h in guest])
    for symbol, doc in docs.items():
        snap = _snapshot_from_library_document(doc)
        if snap is not None:
            _LIBRARY_SNAPSHOTS[_normalize_symbol(symbol)] = snap
    if _LIBRARY_SNAPSHOTS:
        dashboard.library_ready = True


def _apply_portfolio_metrics(dashboard: GuestDashboard) -> None:
    """Set portfolio_value_usd and portfolio_yield_pct from rows / cost basis."""
    total_value = sum(float(getattr(row, "current_value", 0) or 0) for row in dashboard.rows)
    if total_value <= 0:
        total_value = sum(
            h.shares * h.avg_cost_per_share for h in dashboard.holdings if h.avg_cost_per_share > 0
        )
    dashboard.portfolio_value_usd = round(total_value, 2)
    if total_value > 0 and dashboard.annual_income_usd:
        dashboard.portfolio_yield_pct = round(
            dashboard.annual_income_usd / total_value * 100,
            2,
        )
    else:
        dashboard.portfolio_yield_pct = None


def build_guest_dashboard(guest: Sequence[GuestHolding]) -> GuestDashboard:
    """Compute Command Center metrics from the market library, with snapshot fallback."""
    if not guest:
        return GuestDashboard()

    _LIBRARY_SNAPSHOTS.clear()
    scratch = GuestDashboard()
    try:
        _try_enrich_from_library(scratch, guest)
    except (ImportError, AttributeError, SQLiteError, PostgresError, OSError, RuntimeError) as exc:
        logger.warning("Guest demo library overlay failed; using packaged snapshots. (%s)", exc)
        _LIBRARY_SNAPSHOTS.clear()

    dashboard = _build_snapshot_dashboard(guest)
    library_hits = sum(1 for holding in guest if holding.symbol in _LIBRARY_SNAPSHOTS)
    if library_hits:
        dashboard.library_ready = True
        dashboard.data_mode = "library" if library_hits >= len(guest) else "snapshot+enrichment"
        dashboard.provenance_label = (
            "Market library prices and dividends × sample shares · "
            "received cash is a scaled example, not a broker import"
        )
    return dashboard


def migrate_guest_holdings_to_portfolio(db_path: Any) -> int:
    """
    Copy guest session holdings into a new user portfolio after sign-up.

    Returns the number of holdings migrated.
    """
    try:
        import streamlit as st
    except ImportError:
        return 0

    raw = st.session_state.pop(GUEST_SESSION_KEY, None)
    if not raw:
        return 0

    from utils.portfolio_db import holding_count

    if holding_count(db_path) > 0:
        return 0

    from services.portfolio_context import create_portfolio_context

    ctx = create_portfolio_context(db_path=db_path)
    migrated = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        symbol = _normalize_symbol(str(item.get("symbol", "")))
        if not symbol:
            continue
        try:
            ctx.portfolio.upsert_holding(
                symbol,
                shares=float(item.get("shares") or 10.0),
                avg_cost_per_share=float(item.get("avg_cost_per_share") or 0.0),
                company_name=str(item.get("company_name") or item.get("company") or "") or None,
            )
            migrated += 1
        except (SQLiteError, PostgresError, OSError):
            pass
    return migrated
