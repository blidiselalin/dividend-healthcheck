"""
Monthly dividend cash-flow projection for portfolio holdings.
"""

from __future__ import annotations

from utils.chart_theme import style_figure

import calendar
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Set, TYPE_CHECKING

from utils.dividend_amounts import per_payment_amount

if TYPE_CHECKING:
    from data_ingestion.models import DividendRecord, StockDocument
    from data_ingestion.portfolio_store import PortfolioHolding
    from models.stock import StockData


@dataclass(frozen=True)
class HoldingMonthDividend:
    """Expected dividend cash for one holding in a calendar month."""

    symbol: str
    company: str
    shares: float
    expected_cash: float
    per_share: float
    payment_date: Optional[date]
    ex_date: Optional[date]
    status: str  # received | scheduled | projected


@dataclass
class MonthDividendExposure:
    """Aggregated dividend exposure for a single calendar month."""

    month_start: date
    label: str
    total_cash: float
    holdings: List[HoldingMonthDividend] = field(default_factory=list)

    @property
    def payer_count(self) -> int:
        return len(self.holdings)


@dataclass
class PortfolioDividendCalendar:
    """Last, current, and next month dividend expectations."""

    last_month: MonthDividendExposure
    current_month: MonthDividendExposure
    next_month: MonthDividendExposure
    reference_date: date


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def month_end(value: date) -> date:
    last_day = calendar.monthrange(value.year, value.month)[1]
    return date(value.year, value.month, last_day)


def add_months(value: date, months: int) -> date:
    index = value.month - 1 + months
    year = value.year + index // 12
    month = index % 12 + 1
    return date(year, month, 1)


def _cash_date(record: "DividendRecord") -> date:
    if record.payment_date:
        return record.payment_date
    return record.ex_date + timedelta(days=14)


def _in_month(day: date, month: date) -> bool:
    return day.year == month.year and day.month == month.month


def _per_share_payment(
    records: Sequence["DividendRecord"],
    document: Optional["StockDocument"],
    stock: Optional["StockData"],
) -> Optional[float]:
    return per_payment_amount(records, document, stock)


def _typical_payment_months(records: Sequence["DividendRecord"]) -> Set[int]:
    """Calendar months (1–12) that usually include a cash dividend."""
    if not records:
        return set()

    recent = sorted(records, key=lambda record: _cash_date(record))[-36:]
    month_counts = Counter(_cash_date(record).month for record in recent)
    if not month_counts:
        return set()

    max_count = max(month_counts.values())
    if max_count <= 1:
        return set(month_counts.keys())

    threshold = max(1, max_count - 1)
    return {month for month, count in month_counts.items() if count >= threshold}


def _payments_in_month_from_history(
    records: Sequence["DividendRecord"],
    target_month: date,
) -> List[tuple[date, date, float]]:
    """Historical payments whose cash date falls in target_month."""
    matches: List[tuple[date, date, float]] = []
    for record in records:
        cash_day = _cash_date(record)
        if _in_month(cash_day, target_month):
            matches.append((record.ex_date, cash_day, float(record.amount)))
    return matches


def _holding_payments_for_month(
    holding: "PortfolioHolding",
    target_month: date,
    *,
    document: Optional["StockDocument"],
    stock: Optional["StockData"],
    row_ex_date: Optional[date] = None,
    row_pay_date: Optional[date] = None,
) -> List[HoldingMonthDividend]:
    records = list(document.dividend_history) if document and document.dividend_history else []
    company = (
        (document.name if document and document.name else None)
        or (stock.name if stock and stock.name else None)
        or holding.symbol
    )
    today = date.today()
    current_month = month_start(today)
    is_past_month = target_month < current_month
    is_future_month = target_month > current_month

    results: List[HoldingMonthDividend] = []
    seen_keys: Set[str] = set()

    def _add(
        *,
        ex_date: Optional[date],
        pay_date: Optional[date],
        per_share_amount: float,
        status: str,
    ) -> None:
        pay_key = pay_date.isoformat() if pay_date else "unknown"
        key = f"{pay_key}-{per_share_amount:.6f}"
        if key in seen_keys:
            return
        seen_keys.add(key)
        results.append(
            HoldingMonthDividend(
                symbol=holding.symbol,
                company=company,
                shares=holding.shares,
                expected_cash=round(per_share_amount * holding.shares, 2),
                per_share=round(per_share_amount, 4),
                payment_date=pay_date,
                ex_date=ex_date,
                status=status,
            )
        )

    history_payments = _payments_in_month_from_history(records, target_month)
    for ex_date, pay_date, amount in history_payments:
        status = "received" if is_past_month or pay_date <= today else "scheduled"
        _add(ex_date=ex_date, pay_date=pay_date, per_share_amount=amount, status=status)

    # Past months: only cash that actually landed in that month (dividend history).
    if is_past_month:
        return results

    per_share = _per_share_payment(records, document, stock)
    if per_share is None or per_share <= 0:
        return results

    # Current / future: optional announced dates when not already in history.
    if not is_future_month:
        announced_ex = row_ex_date or (document.ex_dividend_date if document else None)
        announced_pay = row_pay_date
        if announced_ex or announced_pay:
            pay = announced_pay or (announced_ex + timedelta(days=14))
            if _in_month(pay, target_month) and not history_payments:
                status = "received" if pay <= today else "scheduled"
                _add(
                    ex_date=announced_ex or (pay - timedelta(days=14)),
                    pay_date=pay,
                    per_share_amount=per_share,
                    status=status,
                )

    if results or is_past_month:
        return results

    typical_months = _typical_payment_months(records)
    if target_month.month not in typical_months:
        return results

    same_calendar_month = [
        record
        for record in records
        if _cash_date(record).month == target_month.month
    ]
    if same_calendar_month:
        recent_same_month = sorted(same_calendar_month, key=lambda r: _cash_date(r))[-3:]
        projected = sum(record.amount for record in recent_same_month) / len(
            recent_same_month
        )
    else:
        projected = per_share

    projected_pay = date(target_month.year, target_month.month, 15)
    status = "scheduled" if not is_future_month else "projected"
    _add(
        ex_date=projected_pay - timedelta(days=14),
        pay_date=projected_pay,
        per_share_amount=projected,
        status=status,
    )

    return results


def _summarize_month(
    holdings: Sequence["PortfolioHolding"],
    target_month: date,
    *,
    vector_docs: Dict[str, "StockDocument"],
    stock_data: Dict[str, "StockData"],
    row_dates: Optional[Dict[str, tuple[Optional[date], Optional[date]]]] = None,
) -> MonthDividendExposure:
    row_dates = row_dates or {}
    payments: List[HoldingMonthDividend] = []

    for holding in holdings:
        doc = vector_docs.get(holding.symbol)
        stock = stock_data.get(holding.symbol)
        ex_date, pay_date = row_dates.get(holding.symbol, (None, None))
        payments.extend(
            _holding_payments_for_month(
                holding,
                target_month,
                document=doc,
                stock=stock,
                row_ex_date=ex_date,
                row_pay_date=pay_date,
            )
        )

    payments.sort(key=lambda item: item.expected_cash, reverse=True)
    total = round(sum(item.expected_cash for item in payments), 2)
    return MonthDividendExposure(
        month_start=target_month,
        label=target_month.strftime("%B %Y"),
        total_cash=total,
        holdings=payments,
    )


def build_portfolio_dividend_calendar(
    holdings: Sequence["PortfolioHolding"],
    *,
    vector_docs: Dict[str, "StockDocument"],
    stock_data: Dict[str, "StockData"],
    row_dates: Optional[Dict[str, tuple[Optional[date], Optional[date]]]] = None,
    reference_date: Optional[date] = None,
) -> PortfolioDividendCalendar:
    """Build last / current / next month dividend exposure for the portfolio."""
    today = reference_date or date.today()
    current = month_start(today)
    last_month = add_months(current, -1)
    next_month = add_months(current, 1)

    return PortfolioDividendCalendar(
        reference_date=today,
        last_month=_summarize_month(
            holdings, last_month, vector_docs=vector_docs, stock_data=stock_data, row_dates=row_dates
        ),
        current_month=_summarize_month(
            holdings, current, vector_docs=vector_docs, stock_data=stock_data, row_dates=row_dates
        ),
        next_month=_summarize_month(
            holdings, next_month, vector_docs=vector_docs, stock_data=stock_data, row_dates=row_dates
        ),
    )


def month_comparison_change_pct(current: float, other: float) -> Optional[float]:
    if other <= 0:
        return None
    return ((current - other) / other) * 100


try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


def create_month_comparison_chart(calendar: PortfolioDividendCalendar):
    """Grouped bar chart: last vs current vs next month total dividend cash."""
    if not PLOTLY_AVAILABLE:
        return None

    months = [calendar.last_month, calendar.current_month, calendar.next_month]
    labels = [month.label for month in months]
    totals = [month.total_cash for month in months]
    colors = ["#90a4ae", "#1976d2", "#43a047"]

    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=totals,
                marker_color=colors,
                text=[f"${value:,.0f}" for value in totals],
                textposition="outside",
                hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Monthly dividend cash expectation",
        yaxis_title="Expected cash (USD)",
        height=360,
        margin=dict(t=50, b=40),
    )
    return style_figure(fig)


def create_month_payers_chart(exposure: MonthDividendExposure):
    """Horizontal bar chart of holdings paying in a given month."""
    if not PLOTLY_AVAILABLE or not exposure.holdings:
        return None

    ordered = sorted(exposure.holdings, key=lambda item: item.expected_cash)
    status_colors = {
        "received": "#2e7d32",
        "scheduled": "#1976d2",
        "projected": "#f9a825",
    }
    colors = [status_colors.get(item.status, "#9e9e9e") for item in ordered]

    fig = go.Figure(
        go.Bar(
            y=[f"{item.symbol}" for item in ordered],
            x=[item.expected_cash for item in ordered],
            orientation="h",
            marker_color=colors,
            customdata=[
                [item.symbol, item.status, item.per_share, item.payment_date]
                for item in ordered
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Status: %{customdata[1]}<br>"
                "$%{x:,.2f} total<br>"
                "$%{customdata[2]:.4f}/share<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=f"Dividend payers — {exposure.label}",
        xaxis_title="Expected cash (USD)",
        height=max(320, 26 * len(ordered)),
        margin=dict(l=10, r=10, t=50, b=40),
    )
    return style_figure(fig)
