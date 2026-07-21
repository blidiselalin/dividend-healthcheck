"""
Session-only guest portfolio for the pre-login Command Center (no account required).

Users can explore up to three dividend stocks; holdings migrate to their account on sign-up.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from sqlite3 import Error as SQLiteError
from typing import Any

try:
    from psycopg import Error as PostgresError
except ImportError:
    PostgresError = type("PostgresError", (Exception,), {})

from data_ingestion.portfolio_store import PortfolioHolding

GUEST_SESSION_KEY = "guest_playground_holdings"
GUEST_SPOTLIGHT_KEY = "guest_playground_spotlight"
GUEST_MAX_HOLDINGS = 3

# Quick-add symbols for beta demo (common dividend names)
BETA_DEMO_SYMBOLS: tuple[str, ...] = (
    "KO",
    "JNJ",
    "O",
    "SCHD",
    "VZ",
    "MSFT",
    "PG",
    "XOM",
    "AAPL",
)

# symbol, company, shares, avg_cost_usd — matches demo portfolio for a rich first paint
DEFAULT_GUEST_HOLDINGS: tuple[tuple[str, str, float, float], ...] = (
    ("KO", "Coca-Cola Co", 25.0, 58.0),
    ("JNJ", "Johnson & Johnson", 10.0, 155.0),
    ("O", "Realty Income Corp", 30.0, 52.0),
)


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
    monthly_forecast: list[tuple[str, float]] = field(default_factory=list)
    next_payouts: list[GuestNextPayout] = field(default_factory=list)
    safety_alerts: list[GuestSafetyAlert] = field(default_factory=list)
    rows: list[Any] = field(default_factory=list)
    library_ready: bool = False


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


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
    avg_cost_per_share: float = 0.0,
    company_name: str = "",
) -> tuple[list[GuestHolding], str | None]:
    """Add or update a guest holding. Returns (holdings, error_message)."""
    symbol = _normalize_symbol(symbol)
    if not symbol:
        return guest_holdings_from_session(session), "Enter a ticker symbol."

    current = guest_holdings_from_session(session)
    if not any(h.symbol == symbol for h in current) and len(current) >= GUEST_MAX_HOLDINGS:
        return (
            current,
            f"Try up to {GUEST_MAX_HOLDINGS} stocks before sign-up — remove one to add another.",
        )

    updated = [h for h in current if h.symbol != symbol]
    updated.append(
        GuestHolding(
            symbol=symbol,
            shares=max(0.0, float(shares)),
            avg_cost_per_share=max(0.0, float(avg_cost_per_share)),
            company_name=company_name or symbol,
        )
    )
    updated.sort(key=lambda h: h.symbol)
    save_guest_holdings(session, updated)
    session[GUEST_SPOTLIGHT_KEY] = symbol
    return updated, None


def remove_guest_holding(session: dict[str, Any], symbol: str) -> list[GuestHolding]:
    symbol = _normalize_symbol(symbol)
    updated = [h for h in guest_holdings_from_session(session) if h.symbol != symbol]
    if not updated:
        updated = default_guest_holdings()
    save_guest_holdings(session, updated)
    return updated


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


def build_guest_dashboard(guest: Sequence[GuestHolding]) -> GuestDashboard:
    """Compute Command Center metrics from the shared library (no user DB)."""
    dashboard = GuestDashboard(holdings=list(guest))
    if not guest:
        return dashboard

    holdings = to_portfolio_holdings(guest)
    try:
        from services.portfolio_details_service import PortfolioDetailsService

        service = PortfolioDetailsService()
        rows, _preload = service.build_rows_with_cache(
            holdings=holdings,
            use_live_prices=False,
            preload_analysis=False,
        )
        dashboard.rows = rows
        dashboard.library_ready = bool(rows)
        dashboard.annual_income_usd = round(
            sum(getattr(row, "annual_income", 0) or 0 for row in rows),
            2,
        )

        symbols = [h.symbol for h in guest]
        vector_docs = service._load_documents(symbols)
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
        dashboard.next_payouts = _next_payouts_from_calendar(calendar)
        dashboard.monthly_forecast = _monthly_forecast_12m(
            holdings,
            vector_docs=vector_docs,
            stock_data=stock_data,
        )
        dashboard.safety_alerts = _safety_alerts_from_rows(rows)
    except (ImportError, AttributeError, SQLiteError, PostgresError, OSError):  # noqa: BLE001
        pass  # Best effort; return partial dashboard on error
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
