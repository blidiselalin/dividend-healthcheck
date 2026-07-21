"""
Resolve dividend ex-dates and payment dates for portfolio cash tracking.

Yahoo Finance dividend series only provides ex-dates; portfolio dashboards
attribute cash to **payment** month. We merge library history, normalized
Postgres tables, local download CSVs, Nasdaq, Yahoo calendar hints, and
symbol-specific ex→pay lag before reconciling stored receipts.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from sqlite3 import Error as SQLiteError
from typing import TYPE_CHECKING, Any

import requests

from data_ingestion.models import DividendRecord, StockDocument
from utils.dividend_amounts import normalize_payment_amount

try:
    from psycopg import Error as PostgresError
except ImportError:
    PostgresError = type("PostgresError", (Exception,), {})

if TYPE_CHECKING:
    from services.portfolio_holding_detail_service import HoldingDividendRow

logger = logging.getLogger(__name__)

_PAYMENT_DATE_CACHE: dict[str, PaymentDateLookup] = {}


@dataclass(frozen=True)
class DividendDateCorrection:
    symbol: str
    ex_date: date
    per_share_usd: float
    old_pay_date: date | None
    new_pay_date: date
    source: str


@dataclass(frozen=True)
class DividendDateReconcileStats:
    symbols_checked: int = 0
    receipts_updated: int = 0
    pay_dates_corrected: int = 0
    nasdaq_lookups: int = 0


@dataclass
class PaymentDateLookup:
    """Merged ex-date (+ amount) → payment date from all available sources."""

    by_ex_amount: dict[tuple[date, float], date] = field(default_factory=dict)
    by_ex: dict[date, date] = field(default_factory=dict)
    ex_to_pay_lags: list[int] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)

    def merge(self, other: PaymentDateLookup, *, source: str) -> None:
        """Add rows from another lookup; existing keys are not overwritten."""
        self.sources.add(source)
        for key, pay in other.by_ex_amount.items():
            self.by_ex_amount.setdefault(key, pay)
            ex, _amount = key
            self.by_ex.setdefault(ex, pay)
            self.ex_to_pay_lags.append((pay - ex).days)
        for ex, pay in other.by_ex.items():
            self.by_ex.setdefault(ex, pay)
            if ex not in {key[0] for key in self.by_ex_amount}:
                self.ex_to_pay_lags.append((pay - ex).days)

    def resolve(self, ex_date: date, amount: float) -> date | None:
        key = (ex_date, _round_amount(amount))
        if key in self.by_ex_amount:
            return self.by_ex_amount[key]
        return self.by_ex.get(ex_date)

    def median_lag_days(self) -> int | None:
        if len(self.ex_to_pay_lags) < 2:
            return None
        ordered = sorted(self.ex_to_pay_lags)
        return ordered[len(ordered) // 2]


def payment_date_for_record(
    record: DividendRecord,
    *,
    estimated_lag_days: int = 14,
) -> date:
    """Cash date for a dividend record (payment date when known)."""
    if record.payment_date:
        return record.payment_date
    return record.ex_date + timedelta(days=estimated_lag_days)


def pay_date_is_estimated(record: DividendRecord) -> bool:
    return record.payment_date is None


def _round_amount(amount: float) -> float:
    return round(float(amount), 4)


def _parse_csv_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_csv_amount(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        amount = float(text)
    except ValueError:
        return None
    return amount if amount > 0 else None


def _lookup_from_rows(
    rows: list[dict[str, Any]],
    *,
    symbol_filter: str | None = None,
) -> PaymentDateLookup:
    lookup = PaymentDateLookup()
    symbol_filter = symbol_filter.strip().upper() if symbol_filter else None

    for row in rows:
        row_symbol = str(row.get("symbol") or row.get("Symbol") or "").strip().upper()
        if symbol_filter and row_symbol and row_symbol != symbol_filter:
            continue

        ex = _parse_csv_date(
            row.get("ex_date") or row.get("Ex-Date") or row.get("ExDate") or row.get("Ex/EFF DATE")
        )
        pay = _parse_csv_date(
            row.get("payment_date")
            or row.get("Payment-Date")
            or row.get("PaymentDate")
            or row.get("PAYMENT DATE")
        )
        amount = _parse_csv_amount(
            row.get("amount") or row.get("Amount") or row.get("CASH AMOUNT") or row.get("Dividend")
        )
        if ex is None or pay is None:
            continue
        if amount is None:
            lookup.by_ex.setdefault(ex, pay)
            lookup.ex_to_pay_lags.append((pay - ex).days)
            continue
        key = (ex, _round_amount(amount))
        lookup.by_ex_amount[key] = pay
        lookup.by_ex.setdefault(ex, pay)
        lookup.ex_to_pay_lags.append((pay - ex).days)

    return lookup


def _lookup_from_dividend_records(records: list[DividendRecord]) -> PaymentDateLookup:
    rows = [
        {
            "ex_date": record.ex_date,
            "payment_date": record.payment_date,
            "amount": record.amount,
        }
        for record in records
        if record.payment_date is not None
    ]
    return _lookup_from_rows(rows)


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        logger.debug("Could not read dividend CSV %s: %s", path, exc)
        return []


def _local_dividend_csv_paths(symbol: str) -> list[Path]:
    from config import DOWNLOADS_DIR

    symbol = symbol.strip().upper()
    symbol_lower = symbol.lower()
    seen: set[Path] = set()
    candidates: list[Path] = [
        DOWNLOADS_DIR / f"{symbol}_dividends.csv",
        DOWNLOADS_DIR / "nasdaq" / f"{symbol}_dividends.csv",
        DOWNLOADS_DIR / "stockquote" / f"dividends_{symbol_lower}.csv",
        DOWNLOADS_DIR / "stockquote" / "dividend_history.csv",
    ]
    for pattern in (
        f"**/{symbol}_dividends.csv",
        f"**/dividends_{symbol_lower}.csv",
    ):
        candidates.extend(DOWNLOADS_DIR.glob(pattern))

    ordered: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            ordered.append(resolved)
    return ordered


def _local_csv_payment_lookup(symbol: str) -> PaymentDateLookup:
    merged = PaymentDateLookup()
    for path in _local_dividend_csv_paths(symbol):
        rows = _read_csv_rows(path)
        if not rows:
            continue
        partial = _lookup_from_rows(rows, symbol_filter=symbol)
        if partial.by_ex_amount or partial.by_ex:
            merged.merge(partial, source=f"csv:{path.name}")
    return merged


def _nasdaq_api_payment_lookup(symbol: str) -> PaymentDateLookup:
    lookup = PaymentDateLookup()
    try:
        from config import DATA_DIR
        from data_ingestion.fetch_nasdaq import NasdaqFetcher

        fetcher = NasdaqFetcher(output_dir=DATA_DIR / "downloads")
        rows = fetcher.fetch_dividend_history(symbol)
        partial = _lookup_from_rows(rows, symbol_filter=symbol)
        if partial.by_ex_amount or partial.by_ex:
            lookup.merge(partial, source="nasdaq_api")
    except (ImportError, requests.exceptions.RequestException) as exc:
        logger.debug("Nasdaq dividend calendar unavailable for %s: %s", symbol, exc)
    return lookup


def _yahoo_payment_lookup(symbol: str) -> PaymentDateLookup:
    lookup = PaymentDateLookup()
    try:
        import yfinance as yf
    except ImportError:
        return lookup

    try:
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        if isinstance(calendar, dict):
            ex = _parse_yahoo_date(calendar.get("Ex-Dividend Date"))
            pay = _parse_yahoo_date(calendar.get("Dividend Date"))
            if ex and pay:
                lookup.by_ex[ex] = pay
                lookup.ex_to_pay_lags.append((pay - ex).days)
                lookup.sources.add("yahoo_calendar")

        info = ticker.info or {}
        ex = _parse_yahoo_timestamp(info.get("exDividendDate"))
        pay = _parse_yahoo_timestamp(info.get("dividendDate"))
        if ex and pay:
            lookup.by_ex.setdefault(ex, pay)
            lookup.ex_to_pay_lags.append((pay - ex).days)
            lookup.sources.add("yahoo_info")
    except (ImportError, yf.exceptions.YFinanceError) as exc:
        logger.debug("Yahoo dividend calendar unavailable for %s: %s", symbol, exc)

    return lookup


def _parse_yahoo_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        try:
            return value.date()
        except (AttributeError, TypeError, ValueError):
            return None
    return _parse_csv_date(value)


def _parse_yahoo_timestamp(value: Any) -> date | None:
    if value in (None, 0, "0"):
        return None
    try:
        return datetime.fromtimestamp(value).date()
    except (TypeError, ValueError, OSError):
        return _parse_yahoo_date(value)


def _build_payment_date_lookup(
    symbol: str,
    *,
    document_records: list[DividendRecord] | None = None,
    fetch_remote: bool = True,
) -> PaymentDateLookup:
    """
    Merge payment calendars from every source we have for ``symbol``.

    Priority (first match wins when resolving): document/postgres rows → local
    CSV downloads → Nasdaq API → Yahoo calendar/info → median lag inference.
    """
    symbol = symbol.strip().upper()
    cached = _PAYMENT_DATE_CACHE.get(symbol)
    if cached is not None and not fetch_remote:
        return cached

    lookup = PaymentDateLookup()

    if document_records:
        known = _lookup_from_dividend_records(document_records)
        if known.by_ex_amount or known.by_ex:
            lookup.merge(known, source="document")

    local = _local_csv_payment_lookup(symbol)
    if local.by_ex_amount or local.by_ex:
        lookup.merge(local, source="local_csv")

    if fetch_remote:
        nasdaq = _nasdaq_api_payment_lookup(symbol)
        if nasdaq.by_ex_amount or nasdaq.by_ex:
            lookup.merge(nasdaq, source="nasdaq_api")

        yahoo = _yahoo_payment_lookup(symbol)
        if yahoo.by_ex or yahoo.by_ex_amount:
            lookup.merge(yahoo, source="yahoo")

    _PAYMENT_DATE_CACHE[symbol] = lookup
    return lookup


def _nasdaq_payment_lookup(symbol: str) -> dict[tuple[date, float], date]:
    """Backward-compatible ex-date + amount → payment date map."""
    lookup = _build_payment_date_lookup(symbol, fetch_remote=True)
    return dict(lookup.by_ex_amount)


def clear_nasdaq_payment_cache() -> None:
    _PAYMENT_DATE_CACHE.clear()


def clear_payment_date_cache() -> None:
    _PAYMENT_DATE_CACHE.clear()


def enrich_document_payment_dates(
    symbol: str,
    document: StockDocument | None,
    *,
    fetch_nasdaq: bool = True,
    reference_date: date | None = None,
) -> StockDocument | None:
    """
    Fill missing payment dates on ``document.dividend_history``.

    Priority: existing payment_date → Postgres history table → local CSV
    downloads → Nasdaq API → Yahoo calendar → symbol median ex→pay lag.
    """
    if document is None or not document.dividend_history:
        return document

    symbol = symbol.strip().upper()
    today = reference_date or date.today()
    cutoff = date(today.year - 3, today.month, today.day)

    try:
        from db.connection import use_cloud_sql

        if use_cloud_sql():
            from db.postgres_market_history_store import PostgresMarketHistoryStore

            document = PostgresMarketHistoryStore().attach_history_to_document(document)
    except (ImportError, SQLiteError, PostgresError, OSError) as exc:
        logger.debug("Could not attach Postgres dividend history for %s: %s", symbol, exc)

    records = list(document.dividend_history)
    payment_lookup = _build_payment_date_lookup(
        symbol,
        document_records=records,
        fetch_remote=fetch_nasdaq,
    )
    median_lag = payment_lookup.median_lag_days()
    stock = None

    for record in records:
        if record.ex_date < cutoff:
            continue
        if record.payment_date and not pay_date_is_estimated(record):
            continue

        per_share = normalize_payment_amount(
            float(record.amount),
            records,
            document,
            stock,
        )
        resolved = payment_lookup.resolve(record.ex_date, per_share)
        if resolved is not None:
            record.payment_date = resolved
            continue

        if median_lag is not None:
            record.payment_date = record.ex_date + timedelta(days=median_lag)

    document.dividend_history = sorted(records, key=lambda item: item.ex_date)
    return document


def build_expected_dividend_rows(
    symbol: str,
    document: StockDocument | None,
    *,
    detail_service: Any,
    current_shares: float,
    tracking_since: date | None,
) -> list[HoldingDividendRow]:
    """Expected paid dividend rows using enriched payment dates."""
    return detail_service.dividend_history(
        symbol,
        document,
        current_shares=current_shares,
        tracking_since=tracking_since,
        prefer_stored=False,
    )


def _fuzzy_match_row(
    receipt_ex: date,
    receipt_pay: date,
    receipt_per_share: float,
    candidates: list[HoldingDividendRow],
) -> HoldingDividendRow | None:
    """Match a stored receipt when ex-date drifted but pay month/amount align."""
    per = round(receipt_per_share, 4)
    for row in candidates:
        if round(row.per_share_usd, 4) != per:
            continue
        if row.ex_date == receipt_ex:
            return row
        if (
            row.pay_date.year == receipt_pay.year
            and row.pay_date.month == receipt_pay.month
            and abs((row.pay_date - receipt_pay).days) <= 7
        ):
            return row
    return None


def reconcile_receipt_dates(
    ctx: Any,
    holdings: list[Any],
    documents: dict[str, StockDocument | None],
    *,
    fetch_nasdaq: bool = True,
    reference_date: date | None = None,
) -> DividendDateReconcileStats:
    """
    Align ``dividend_receipts`` pay/ex dates and cash with enriched library data.
    """
    today = reference_date or date.today()
    stats = DividendDateReconcileStats()
    corrections: list[DividendDateCorrection] = []

    for holding in holdings:
        symbol = holding.symbol.strip().upper()
        document = documents.get(symbol) or documents.get(holding.symbol)
        document = enrich_document_payment_dates(
            symbol,
            document,
            fetch_nasdaq=fetch_nasdaq,
            reference_date=today,
        )
        if document is not None:
            documents[symbol] = document

        expected_rows = build_expected_dividend_rows(
            symbol,
            document,
            detail_service=ctx.detail,
            current_shares=holding.shares,
            tracking_since=holding.dividend_tracking_since,
        )
        expected_paid = [row for row in expected_rows if row.pay_date <= today]
        if not expected_paid:
            continue

        stats = DividendDateReconcileStats(
            symbols_checked=stats.symbols_checked + 1,
            receipts_updated=stats.receipts_updated,
            pay_dates_corrected=stats.pay_dates_corrected,
            nasdaq_lookups=stats.nasdaq_lookups + (1 if fetch_nasdaq else 0),
        )

        by_key = {(row.ex_date, round(row.per_share_usd, 6)): row for row in expected_paid}
        stored = ctx.receipts.list_for_symbol(symbol)

        for receipt in stored:
            key = (receipt.ex_date, round(receipt.per_share_usd, 6))
            expected = by_key.get(key) or _fuzzy_match_row(
                receipt.ex_date,
                receipt.pay_date,
                receipt.per_share_usd,
                expected_paid,
            )
            if expected is None:
                continue

            if (
                receipt.pay_date == expected.pay_date
                and receipt.ex_date == expected.ex_date
                and receipt.shares_held == expected.shares_held
                and receipt.gross_usd == expected.cash_usd
            ):
                continue

            updated = ctx.receipts.update_receipt(
                receipt.id,
                ex_date=expected.ex_date,
                pay_date=expected.pay_date,
                per_share_usd=expected.per_share_usd,
                shares_held=expected.shares_held,
                gross_usd=expected.cash_usd,
            )
            if not updated:
                continue

            stats = DividendDateReconcileStats(
                symbols_checked=stats.symbols_checked,
                receipts_updated=stats.receipts_updated + 1,
                pay_dates_corrected=stats.pay_dates_corrected
                + (1 if receipt.pay_date != expected.pay_date else 0),
                nasdaq_lookups=stats.nasdaq_lookups,
            )
            if receipt.pay_date != expected.pay_date:
                corrections.append(
                    DividendDateCorrection(
                        symbol=symbol,
                        ex_date=expected.ex_date,
                        per_share_usd=expected.per_share_usd,
                        old_pay_date=receipt.pay_date,
                        new_pay_date=expected.pay_date,
                        source="library+sources",
                    )
                )

    if corrections:
        sample = corrections[:5]
        logger.info(
            "Dividend date reconcile: %d symbols, %d receipts updated (%d pay-date fixes). "
            "Examples: %s",
            stats.symbols_checked,
            stats.receipts_updated,
            stats.pay_dates_corrected,
            ", ".join(f"{item.symbol} {item.old_pay_date}→{item.new_pay_date}" for item in sample),
        )

    return stats
