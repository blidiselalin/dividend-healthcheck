"""
Session-only guest portfolio for the pre-login Command Center (no account required).

Users can explore up to three dividend stocks; holdings migrate to their account on sign-up.
Public demo metrics are snapshot-first so the MVP works without the market library.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
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
GUEST_MAX_HOLDINGS = 3
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
    ("O", "Realty Income Corp", 30.0, 52.0),
)


@dataclass(frozen=True)
class DemoSymbolSnapshot:
    """Illustrative per-share metrics for the public demo (not live market data)."""

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


# Deterministic educational snapshots — no external API required.
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
            "Payout ratio 84% in the sample snapshot — REIT distributions leave less "
            "room if AFFO softens. Educational review aid only."
        ),
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
            "Sample yield 6.4% with elevated payout — verify sustainability before "
            "treating income as durable. Educational only."
        ),
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
        alert_message="Energy cash flows are cyclical in this sample — review coverage.",
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


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def demo_snapshot_for(symbol: str) -> DemoSymbolSnapshot | None:
    return _DEMO_SNAPSHOTS.get(_normalize_symbol(symbol))


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
        if snap.alert_severity in {"high", "medium"} or snap.payout_ratio_pct >= 80:
            alerts.append(
                GuestSafetyAlert(
                    symbol=holding.symbol,
                    company=holding.company_name or snap.company,
                    message=snap.alert_message,
                    severity=snap.alert_severity,
                    suggested_check=(
                        f"Open Research for {holding.symbol} and compare payout, yield, "
                        "and dividend history."
                    ),
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
        next_payouts=payouts[:8],
        safety_alerts=alerts[:6],
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


def _monthly_forecast_12m(
    holdings: list[PortfolioHolding],
    *,
    vector_docs: dict[str, Any],
    stock_data: dict[str, Any],
) -> list[tuple[str, float]]:
    from services.portfolio_dividend_calendar import _summarize_month, add_months, month_start
    from services.portfolio_holding_detail_service import PortfolioHoldingDetailService

    today = date.today()
    start = month_start(today)
    detail = PortfolioHoldingDetailService()
    forecast: list[tuple[str, float]] = []
    for offset in range(12):
        target = add_months(start, offset)
        exposure = _summarize_month(
            holdings,
            target,
            vector_docs=vector_docs,
            stock_data=stock_data,
            reference_date=today,
            detail_service=detail,
        )
        forecast.append((target.strftime("%b %Y"), round(exposure.total_cash, 2)))
    return forecast


def _safety_alerts_from_rows(rows: Sequence[Any]) -> list[GuestSafetyAlert]:
    alerts: list[GuestSafetyAlert] = []
    for row in rows:
        symbol = getattr(row, "ticker", "")
        company = getattr(row, "company", symbol) or symbol
        payout = getattr(row, "payout_ratio_pct", None)
        if payout is not None and payout > 85:
            alerts.append(
                GuestSafetyAlert(
                    symbol=symbol,
                    company=company,
                    message=f"Payout ratio {payout:.0f}% — dividend may have less room to grow.",
                    severity="high" if payout > 95 else "medium",
                    suggested_check=f"Open Research for {symbol} and review payout vs peers.",
                )
            )
        profit = getattr(row, "profit_pct", None)
        if profit is not None and profit < -15:
            alerts.append(
                GuestSafetyAlert(
                    symbol=symbol,
                    company=company,
                    message=f"Position down {profit:.1f}% vs cost — review sizing and safety.",
                    severity="medium",
                    suggested_check=f"Open Research for {symbol} and check yield-channel context.",
                )
            )
        yld = getattr(row, "dividend_yield_pct", None)
        if yld is not None and yld > 8:
            alerts.append(
                GuestSafetyAlert(
                    symbol=symbol,
                    company=company,
                    message=f"Yield {yld:.1f}% is unusually high — verify sustainability.",
                    severity="medium",
                    suggested_check=f"Open Research for {symbol} and inspect coverage evidence.",
                )
            )
    return alerts[:6]


def _next_payouts_from_calendar(calendar: Any) -> list[GuestNextPayout]:
    payouts: list[GuestNextPayout] = []
    for month_label, month in (
        ("This month", calendar.current_month),
        ("Next month", calendar.next_month),
    ):
        for item in getattr(month, "holdings", []) or []:
            if getattr(item, "expected_cash", 0) <= 0:
                continue
            payouts.append(
                GuestNextPayout(
                    symbol=getattr(item, "symbol", ""),
                    company=getattr(item, "company", "") or getattr(item, "symbol", ""),
                    pay_date=getattr(item, "pay_date", None),
                    amount_usd=float(getattr(item, "expected_cash", 0) or 0),
                    status=getattr(item, "status", month_label),
                )
            )
    payouts.sort(key=lambda p: (p.pay_date or date.max, -p.amount_usd))
    return payouts[:8]


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


def _try_enrich_from_library(dashboard: GuestDashboard, guest: Sequence[GuestHolding]) -> None:
    """Best-effort library enrichment — never clears snapshot metrics on failure."""
    holdings = to_portfolio_holdings(guest)
    from services.portfolio_details_service import PortfolioDetailsService

    service = PortfolioDetailsService()
    rows, _preload = service.build_rows_with_cache(
        holdings=holdings,
        use_live_prices=False,
        preload_analysis=False,
    )
    if not rows:
        logger.warning("Guest demo library enrichment returned no rows; keeping snapshot.")
        return

    lib_annual = round(sum(getattr(row, "annual_income", 0) or 0 for row in rows), 2)
    if lib_annual <= 0 and dashboard.annual_income_usd > 0:
        logger.warning(
            "Guest demo library annual income empty; keeping snapshot income %.2f",
            dashboard.annual_income_usd,
        )
        dashboard.data_mode = "snapshot+enrichment"
        dashboard.library_ready = True
        dashboard.provenance_label = (
            "Snapshot income · library rows available for research · sample data"
        )
        return

    symbols = [h.symbol for h in guest]
    vector_docs, _dividend_statuses = service._load_documents(symbols)
    from services.stock_analysis_service import load_portfolio_statistics_stock

    stock_data: dict[str, Any] = {}
    for row in rows:
        stats = load_portfolio_statistics_stock(row.ticker, vector_docs.get(row.ticker))
        if stats is not None:
            stock_data[row.ticker] = stats

    from services.portfolio_dividend_calendar import build_portfolio_dividend_calendar

    calendar = build_portfolio_dividend_calendar(
        holdings,
        vector_docs=vector_docs,
        stock_data=stock_data,
    )
    lib_payouts = _next_payouts_from_calendar(calendar)
    lib_forecast = _monthly_forecast_12m(
        holdings,
        vector_docs=vector_docs,
        stock_data=stock_data,
    )
    lib_alerts = _safety_alerts_from_rows(rows)

    dashboard.rows = rows
    dashboard.library_ready = True
    dashboard.annual_income_usd = lib_annual
    if lib_payouts:
        dashboard.next_payouts = lib_payouts
        dashboard.near_term_income_usd = round(sum(p.amount_usd for p in lib_payouts[:3]), 2)
    if lib_forecast and any(v > 0 for _, v in lib_forecast):
        dashboard.monthly_forecast = lib_forecast
    if lib_alerts or not dashboard.safety_alerts:
        dashboard.safety_alerts = lib_alerts
    dashboard.data_mode = "library"
    dashboard.provenance_label = (
        "Shared market library · educational estimates · not a broker account"
    )
    # Keep illustrative received sample proportional to library annual income.
    dashboard.sample_received_gross_usd = round(lib_annual * 0.25, 2)
    dashboard.sample_withholding_usd = round(dashboard.sample_received_gross_usd * 0.15, 2)
    dashboard.sample_received_net_usd = round(
        dashboard.sample_received_gross_usd - dashboard.sample_withholding_usd, 2
    )
    _apply_portfolio_metrics(dashboard)


def build_guest_dashboard(guest: Sequence[GuestHolding]) -> GuestDashboard:
    """Compute Command Center metrics — snapshot first, optional library enrichment."""
    if not guest:
        return GuestDashboard()

    dashboard = _build_snapshot_dashboard(guest)
    try:
        _try_enrich_from_library(dashboard, guest)
    except (ImportError, AttributeError, SQLiteError, PostgresError, OSError, RuntimeError) as exc:
        logger.warning("Guest demo library enrichment failed; using snapshot. (%s)", exc)
        dashboard.data_mode = "snapshot"
        dashboard.library_ready = False
        dashboard.provenance_label = (
            "Illustrative snapshot · market library unavailable · sample data only"
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
