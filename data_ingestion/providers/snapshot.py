"""
Canonical partial stock record shared by all data providers.

Providers map vendor-specific JSON into ``StockSnapshot``; merge logic applies
non-null fields onto ``StockDocument`` without overwriting populated values.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from typing import Any

from config import MIN_YIELD_DIVIDEND_PAYMENTS, MIN_YIELD_PRICE_POINTS
from data_ingestion.models import (
    DataSource,
    DividendRecord,
    PriceHistory,
    StockDocument,
)

# Field groups used to decide which provider to call for gap-filling.
FIELD_GROUPS: dict[str, frozenset[str]] = {
    "identity": frozenset({"name", "sector", "industry", "exchange", "description"}),
    "dividend": frozenset(
        {
            "dividend_yield",
            "annual_dividend",
            "payout_ratio",
            "fcf_payout_ratio",
            "dividend_coverage",
            "ex_dividend_date",
            "payment_frequency",
            "dividend_streak_years",
            "dividend_cagr_5y",
            "dividend_cagr_10y",
            "dividend_total_years",
        }
    ),
    "price": frozenset(
        {
            "current_price",
            "market_cap",
            "fifty_two_week_high",
            "fifty_two_week_low",
            "beta",
        }
    ),
    "valuation": frozenset(
        {
            "pe_ratio",
            "forward_pe",
            "peg_ratio",
            "price_to_book",
            "price_to_sales",
            "ev_ebitda",
        }
    ),
    "health": frozenset(
        {
            "debt_to_equity",
            "debt_to_ebitda",
            "interest_coverage",
            "current_ratio",
            "quick_ratio",
        }
    ),
    "profitability": frozenset(
        {
            "roe",
            "roa",
            "roic",
            "profit_margin",
            "operating_margin",
            "gross_margin",
        }
    ),
    "growth": frozenset({"revenue_growth", "earnings_growth", "fcf_growth"}),
    "performance": frozenset(
        {"price_return_1y", "total_return_1y", "price_return_5y", "total_return_5y"}
    ),
    "analyst": frozenset({"target_price", "target_upside", "analyst_rating", "num_analysts"}),
    "history": frozenset({"price_history", "dividend_history"}),
}


@dataclass
class StockSnapshot:
    """Vendor-neutral partial stock record."""

    symbol: str
    source: DataSource = DataSource.MANUAL
    fetched_at: datetime = field(default_factory=datetime.now)

    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    description: str | None = None

    dividend_yield: float | None = None
    annual_dividend: float | None = None
    payout_ratio: float | None = None
    fcf_payout_ratio: float | None = None
    dividend_coverage: float | None = None
    ex_dividend_date: date | None = None
    payment_frequency: int | None = None
    dividend_streak_years: int | None = None
    dividend_cagr_5y: float | None = None
    dividend_cagr_10y: float | None = None
    dividend_total_years: int | None = None

    current_price: float | None = None
    market_cap: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    beta: float | None = None

    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    ev_ebitda: float | None = None

    debt_to_equity: float | None = None
    debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None

    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    gross_margin: float | None = None

    revenue_growth: float | None = None
    earnings_growth: float | None = None
    fcf_growth: float | None = None

    price_return_1y: float | None = None
    total_return_1y: float | None = None
    price_return_5y: float | None = None
    total_return_5y: float | None = None

    target_price: float | None = None
    target_upside: float | None = None
    analyst_rating: str | None = None
    num_analysts: int | None = None

    price_history: list[PriceHistory] = field(default_factory=list)
    dividend_history: list[DividendRecord] = field(default_factory=list)

    def populated_scalar_fields(self) -> set[str]:
        names: set[str] = set()
        for item in fields(self):
            if item.name in (
                "symbol",
                "source",
                "fetched_at",
                "price_history",
                "dividend_history",
            ):
                continue
            if getattr(self, item.name) is not None:
                names.add(item.name)
        return names

    def merge_from(self, other: StockSnapshot, *, prefer: bool = False) -> None:
        """Fill null fields from ``other`` (later sources only fill gaps unless prefer=True)."""
        for item in fields(self):
            name = item.name
            if name in ("symbol", "source", "fetched_at"):
                continue
            if name in ("price_history", "dividend_history"):
                continue
            current = getattr(self, name)
            incoming = getattr(other, name)
            if incoming is None:
                continue
            if current is None or prefer:
                setattr(self, name, incoming)

        self._merge_history(other)

    def _merge_history(self, other: StockSnapshot) -> None:
        from utils.datetime_compat import coerce_calendar_date

        if other.price_history:
            existing = {coerce_calendar_date(point.date) for point in self.price_history}
            for point in other.price_history:
                point_date = coerce_calendar_date(point.date)
                if point_date not in existing:
                    self.price_history.append(point)
            self.price_history.sort(
                key=lambda point: coerce_calendar_date(point.date),
                reverse=True,
            )

        if other.dividend_history:
            existing = {coerce_calendar_date(record.ex_date) for record in self.dividend_history}
            for record in other.dividend_history:
                ex_date = coerce_calendar_date(record.ex_date)
                if ex_date not in existing:
                    self.dividend_history.append(record)
            self.dividend_history.sort(
                key=lambda record: coerce_calendar_date(record.ex_date),
                reverse=True,
            )


def missing_field_groups(doc: StockDocument) -> list[str]:
    """Return field groups that still have gaps on ``doc``."""
    missing: list[str] = []

    def _empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and (not value or value == "Unknown"):
            return True
        return bool(isinstance(value, list) and len(value) == 0)

    checks = {
        "identity": _empty(doc.name) or doc.name == doc.symbol or doc.sector == "Unknown",
        "dividend": _empty(doc.dividend_yield) and _empty(doc.annual_dividend),
        "price": _empty(doc.current_price),
        "valuation": _empty(doc.pe_ratio) and _empty(doc.forward_pe),
        "health": _empty(doc.debt_to_equity) and _empty(doc.current_ratio),
        "profitability": _empty(doc.roe) and _empty(doc.profit_margin),
        "growth": _empty(doc.revenue_growth) and _empty(doc.earnings_growth),
        "performance": _empty(doc.price_return_1y),
        "analyst": _empty(doc.analyst_rating) and _empty(doc.target_price),
        "history": (
            len(doc.price_history) < MIN_YIELD_PRICE_POINTS
            or len(doc.dividend_history) < MIN_YIELD_DIVIDEND_PAYMENTS
        ),
    }
    for group, is_missing in checks.items():
        if is_missing:
            missing.append(group)
    return missing


def apply_snapshot_to_document(doc: StockDocument, snapshot: StockSnapshot) -> StockDocument:  # noqa: C901
    """Apply snapshot fields onto ``doc`` without overwriting existing values."""
    from utils.datetime_compat import max_datetime

    if doc.name == doc.symbol and snapshot.name:
        doc.name = snapshot.name
    if doc.sector == "Unknown" and snapshot.sector:
        doc.sector = snapshot.sector
    if doc.industry == "Unknown" and snapshot.industry:
        doc.industry = snapshot.industry
    if doc.exchange == "Unknown" and snapshot.exchange:
        doc.exchange = snapshot.exchange
    if not doc.description and snapshot.description:
        doc.description = snapshot.description

    scalar_names = {
        item.name
        for item in fields(StockSnapshot)
        if item.name
        not in (
            "symbol",
            "source",
            "fetched_at",
            "price_history",
            "dividend_history",
            "name",
            "sector",
            "industry",
            "exchange",
            "description",
        )
    }
    for name in scalar_names:
        if getattr(doc, name) is None:
            value = getattr(snapshot, name)
            if value is not None:
                setattr(doc, name, value)

    if snapshot.payment_frequency is not None and doc.payment_frequency == 4:
        doc.payment_frequency = snapshot.payment_frequency

    snapshot_copy = StockSnapshot(symbol=doc.symbol)
    snapshot_copy.price_history = list(doc.price_history)
    snapshot_copy.dividend_history = list(doc.dividend_history)
    snapshot_copy.merge_from(snapshot)
    doc.price_history = snapshot_copy.price_history
    doc.dividend_history = snapshot_copy.dividend_history

    if snapshot.source != DataSource.MANUAL:
        doc.source = snapshot.source
    doc.last_updated = max_datetime(doc.last_updated, snapshot.fetched_at)
    return doc


def snapshot_from_document(doc: StockDocument) -> StockSnapshot:
    """Build a snapshot from an existing document (for merge tests)."""
    values: dict[str, Any] = {"symbol": doc.symbol, "source": doc.source}
    for item in fields(StockSnapshot):
        if item.name in ("symbol", "source", "fetched_at"):
            continue
        values[item.name] = getattr(doc, item.name, None)
    snap = StockSnapshot(
        **{k: v for k, v in values.items() if k in {f.name for f in fields(StockSnapshot)}}
    )
    snap.price_history = list(doc.price_history)
    snap.dividend_history = list(doc.dividend_history)
    return snap
