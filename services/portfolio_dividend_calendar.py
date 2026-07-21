"""
Monthly dividend cash-flow projection for portfolio holdings.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from utils.chart_theme import outside_bar_text, style_figure
from utils.dividend_amounts import (
    expected_payment_months,
    normalize_payment_amount,
    per_payment_amount,
)

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
    payment_date: date | None
    ex_date: date | None
    status: str  # received | scheduled | projected


_STATUS_RANK = {"received": 0, "scheduled": 1, "projected": 2}


@dataclass
class MonthDividendExposure:
    """Aggregated dividend exposure for a single calendar month."""

    month_start: date
    label: str
    total_cash: float
    holdings: list[HoldingMonthDividend] = field(default_factory=list)

    @property
    def payer_count(self) -> int:
        return len(self.holdings)

    @property
    def received_cash(self) -> float:
        """Cash from payments already received this month (pay date on or before today)."""
        return round(
            sum(item.expected_cash for item in self.holdings if item.status == "received"),
            2,
        )

    @property
    def received_payer_count(self) -> int:
        return sum(1 for item in self.holdings if item.status == "received")

    @property
    def scheduled_cash(self) -> float:
        return round(
            sum(item.expected_cash for item in self.holdings if item.status == "scheduled"),
            2,
        )

    @property
    def projected_cash(self) -> float:
        return round(
            sum(item.expected_cash for item in self.holdings if item.status == "projected"),
            2,
        )

    @property
    def confirmed_cash(self) -> float:
        """Received or announced this month — excludes pattern projections."""
        return round(self.received_cash + self.scheduled_cash, 2)

    @property
    def confirmed_payer_count(self) -> int:
        return sum(1 for item in self.holdings if item.status in {"received", "scheduled"})


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


def _cash_date(record: DividendRecord) -> date:
    if record.payment_date:
        return record.payment_date
    return record.ex_date + timedelta(days=14)


def _in_month(day: date, month: date) -> bool:
    return day.year == month.year and day.month == month.month


def _per_share_payment(
    records: Sequence[DividendRecord],
    document: StockDocument | None,
    stock: StockData | None,
) -> float | None:
    return per_payment_amount(records, document, stock)


def _shares_for_payment(
    holding: PortfolioHolding,
    *,
    as_of: date,
    detail_service: Any,
) -> float:
    """Shares held on the payment date (journal lots when available)."""
    from services.portfolio_holding_detail_service import shares_as_of

    lots = detail_service.estimated_lots_for_symbol(holding.symbol)
    fallback = holding.shares if not lots else 0.0
    return shares_as_of(lots, as_of, fallback_shares=fallback)


def _collapse_symbol_payments(
    payments: list[HoldingMonthDividend],
) -> list[HoldingMonthDividend]:
    """Keep one payment row per symbol — prefer received, then largest plausible cash."""
    merged: dict[str, HoldingMonthDividend] = {}
    for item in payments:
        existing = merged.get(item.symbol)
        if existing is None:
            merged[item.symbol] = item
            continue
        if _STATUS_RANK[item.status] < _STATUS_RANK[existing.status] or (
            _STATUS_RANK[item.status] == _STATUS_RANK[existing.status]
            and item.per_share <= existing.per_share
        ):
            merged[item.symbol] = item
    return list(merged.values())


def _holding_payments_for_month(  # noqa: C901
    holding: PortfolioHolding,
    target_month: date,
    *,
    document: StockDocument | None,
    stock: StockData | None,
    row_ex_date: date | None = None,
    row_pay_date: date | None = None,
    reference_date: date,
    detail_service: Any,
) -> list[HoldingMonthDividend]:
    records = list(document.dividend_history) if document and document.dividend_history else []
    company = (
        (document.name if document and document.name else None)
        or (stock.name if stock and stock.name else None)
        or holding.company_name
        or holding.symbol
    )
    current_month = month_start(reference_date)
    is_past_month = target_month < current_month
    is_future_month = target_month > current_month

    results: list[HoldingMonthDividend] = []
    seen_keys: set[str] = set()

    def _add(
        *,
        ex_date: date | None,
        pay_date: date | None,
        per_share_amount: float,
        status: str,
        shares: float,
    ) -> None:
        if shares <= 0 or per_share_amount <= 0:
            return
        pay_key = pay_date.isoformat() if pay_date else "unknown"
        key = f"{pay_key}-{per_share_amount:.6f}"
        if key in seen_keys:
            return
        seen_keys.add(key)
        results.append(
            HoldingMonthDividend(
                symbol=holding.symbol,
                company=company,
                shares=round(shares, 4),
                expected_cash=round(per_share_amount * shares, 2),
                per_share=round(per_share_amount, 4),
                payment_date=pay_date,
                ex_date=ex_date,
                status=status,
            )
        )

    for record in records:
        pay_date = _cash_date(record)
        if not _in_month(pay_date, target_month):
            continue
        amount = normalize_payment_amount(float(record.amount), records, document, stock)
        shares = _shares_for_payment(holding, as_of=record.ex_date, detail_service=detail_service)
        status = "received" if is_past_month or pay_date <= reference_date else "scheduled"
        _add(
            ex_date=record.ex_date,
            pay_date=pay_date,
            per_share_amount=amount,
            status=status,
            shares=shares,
        )

    if is_past_month:
        return _collapse_symbol_payments(results)

    per_share = _per_share_payment(records, document, stock)
    if per_share is None or per_share <= 0:
        return _collapse_symbol_payments(results)

    if not is_future_month and not results:
        announced_ex = row_ex_date or (document.ex_dividend_date if document else None)
        announced_pay = row_pay_date
        if announced_ex or announced_pay:
            pay = announced_pay or (announced_ex + timedelta(days=14) if announced_ex else None)
            if pay and _in_month(pay, target_month):
                as_of_date = announced_ex if announced_ex else pay
                if as_of_date:
                    shares = _shares_for_payment(
                        holding,
                        as_of=as_of_date,
                        detail_service=detail_service,
                    )
                    status = "received" if pay <= reference_date else "scheduled"
                    ex_date_val = announced_ex if announced_ex else (pay - timedelta(days=14))
                    _add(
                        ex_date=ex_date_val,
                        pay_date=pay,
                        per_share_amount=per_share,
                        status=status,
                        shares=shares,
                    )

    if results:
        return _collapse_symbol_payments(results)

    payment_months = expected_payment_months(
        records,
        stored_frequency=document.payment_frequency if document else None,
    )
    if target_month.month not in payment_months:
        return results

    same_calendar_month = [
        record for record in records if _cash_date(record).month == target_month.month
    ]
    if same_calendar_month:
        recent_same_month = sorted(same_calendar_month, key=lambda r: _cash_date(r))[-3:]
        projected = normalize_payment_amount(
            sum(record.amount for record in recent_same_month) / len(recent_same_month),
            records,
            document,
            stock,
        )
    else:
        projected = per_share

    projected_pay = date(target_month.year, target_month.month, 15)
    shares = _shares_for_payment(
        holding,
        as_of=projected_pay - timedelta(days=14),
        detail_service=detail_service,
    )
    status = "projected" if is_future_month else "scheduled"
    _add(
        ex_date=projected_pay - timedelta(days=14),
        pay_date=projected_pay,
        per_share_amount=projected,
        status=status,
        shares=shares,
    )
    return _collapse_symbol_payments(results)


def _summarize_month(
    holdings: Sequence[PortfolioHolding],
    target_month: date,
    *,
    vector_docs: dict[str, StockDocument],
    stock_data: dict[str, StockData],
    row_dates: dict[str, tuple[date | None, date | None]] | None = None,
    reference_date: date,
    detail_service: Any,
) -> MonthDividendExposure:
    row_dates = row_dates or {}
    payments: list[HoldingMonthDividend] = []

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
                reference_date=reference_date,
                detail_service=detail_service,
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
    holdings: Sequence[PortfolioHolding],
    *,
    vector_docs: dict[str, StockDocument],
    stock_data: dict[str, StockData],
    row_dates: dict[str, tuple[date | None, date | None]] | None = None,
    reference_date: date | None = None,
) -> PortfolioDividendCalendar:
    """Build last / current / next month dividend exposure for the portfolio."""
    from services.portfolio_holding_detail_service import PortfolioHoldingDetailService

    today = reference_date or date.today()
    current = month_start(today)
    last_month = add_months(current, -1)
    next_month = add_months(current, 1)
    detail_service = PortfolioHoldingDetailService()

    return PortfolioDividendCalendar(
        reference_date=today,
        last_month=_summarize_month(
            holdings,
            last_month,
            vector_docs=vector_docs,
            stock_data=stock_data,
            row_dates=row_dates,
            reference_date=today,
            detail_service=detail_service,
        ),
        current_month=_summarize_month(
            holdings,
            current,
            vector_docs=vector_docs,
            stock_data=stock_data,
            row_dates=row_dates,
            reference_date=today,
            detail_service=detail_service,
        ),
        next_month=_summarize_month(
            holdings,
            next_month,
            vector_docs=vector_docs,
            stock_data=stock_data,
            row_dates=row_dates,
            reference_date=today,
            detail_service=detail_service,
        ),
    )


def month_comparison_change_pct(current: float, other: float) -> float | None:
    if other <= 0:
        return None
    return ((current - other) / other) * 100


try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


def create_month_comparison_chart(calendar: PortfolioDividendCalendar) -> Any:
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
                hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
                **outside_bar_text(),
            )
        ]
    )
    fig.update_layout(
        title="Monthly Dividend Cash — Previous / Current / Next Month",
        yaxis_title="Expected Cash (USD)",
        height=360,
        margin={"t": 60, "b": 40},
    )
    return style_figure(fig)


def create_month_payers_chart(exposure: MonthDividendExposure) -> Any:
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
                [item.symbol, item.status, item.per_share, item.payment_date] for item in ordered
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
        title=f"Dividend Payers — {exposure.label}",
        xaxis_title="Expected Cash (USD)",
        height=max(320, 26 * len(ordered)),
        margin={"l": 10, "r": 60, "t": 60, "b": 40},
    )
    return style_figure(fig)
