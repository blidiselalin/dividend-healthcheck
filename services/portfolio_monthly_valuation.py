"""
Month-end portfolio value from purchase journal share counts and library prices.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from data_ingestion.deposits_store import MonthlyDeposit
from data_ingestion.portfolio_store import PortfolioStore
from data_ingestion.purchase_journal_store import PurchaseJournalStore, PurchaseRecord
from services.portfolio_purchase_journal_service import PortfolioPurchaseJournalService

logger = logging.getLogger(__name__)


# Prefer library history with at least ~1 year of trading days.
_MIN_LIBRARY_BARS = 52
# Relative tolerance when cross-checking primary vs secondary month-end closes.
_PRICE_CROSSCHECK_TOLERANCE = 0.03
_REMOTE_SERIES_CACHE: dict[str, list[tuple[date, float]]] = {}


@dataclass(frozen=True)
class MonthPortfolioValuation:
    portfolio_usd: float
    portfolio_eur: float
    symbols_held: int
    symbols_priced: int
    library_priced: int = 0
    remote_priced: int = 0
    journal_priced: int = 0
    validation_status: str = "unchecked"
    validation_note: str = ""

    @property
    def coverage(self) -> float:
        if self.symbols_held <= 0:
            return 0.0
        return self.symbols_priced / self.symbols_held

    @property
    def mark_quality_label(self) -> str:
        if self.symbols_priced <= 0:
            return "unavailable"
        if self.journal_priced > 0 and self.library_priced + self.remote_priced == 0:
            return "trade-price fallback"
        if self.validation_status == "ok":
            return "validated"
        if self.validation_status == "warning":
            return "cross-check warning"
        if self.validation_status == "failed":
            return "cross-check failed"
        if self.coverage >= 1.0 and self.library_priced + self.remote_priced >= self.symbols_priced:
            return "market closes"
        return "partial"


@dataclass(frozen=True)
class ValuationQualityReport:
    months_valued: int
    months_full_coverage: int
    months_validated_ok: int
    months_with_warnings: int
    library_marks: int
    remote_marks: int
    journal_marks: int
    note: str

    @property
    def status(self) -> str:
        if self.months_valued <= 0:
            return "unavailable"
        if self.months_with_warnings > 0:
            return "warning"
        if self.months_full_coverage == self.months_valued and self.journal_marks == 0:
            return "ok"
        if self.months_full_coverage == self.months_valued:
            return "ok"
        return "partial"


def month_end(day: date) -> date:
    last = calendar.monthrange(day.year, day.month)[1]
    return date(day.year, day.month, last)


def _month_start(day: date) -> date:
    return date(day.year, day.month, 1)


def portfolio_inception_period(deposits: list[MonthlyDeposit]) -> date | None:
    """
    First calendar month with a positive deposit inflow.

    Used to hide pre-inception placeholder months (e.g. IBKR statement period
    starting before the first cash transfer).
    """
    inception: date | None = None
    for item in deposits:
        if item.deposit_eur > 0.01 or item.deposit_usd > 0.01:
            candidate = _month_start(item.period)
            if inception is None or candidate < inception:
                inception = candidate
    return inception


def continuous_monthly_deposits(
    deposits: list[MonthlyDeposit],
    *,
    include_current_month: bool = True,
    reference: date | None = None,
    trim_before_inception: bool = True,
) -> list[MonthlyDeposit]:
    """
    Expand sparse deposit history into every calendar month from first to last.

    Missing months are returned as zero-deposit placeholders so evolution charts
    can show portfolio value even when no cash was added that month.
    """
    if not deposits:
        return []
    ordered = sorted(deposits, key=lambda item: (item.period.year, item.period.month))
    by_key = {item.period_key: item for item in ordered}
    start = _month_start(ordered[0].period)
    if trim_before_inception:
        inception = portfolio_inception_period(deposits)
        if inception is not None and inception > start:
            start = inception
    end = _month_start(ordered[-1].period)
    if include_current_month:
        today = reference or date.today()
        current_month = date(today.year, today.month, 1)
        if current_month > end:
            end = current_month
    out: list[MonthlyDeposit] = []
    sort_order = 1
    year, month = start.year, start.month
    end_key = (end.year, end.month)
    while (year, month) <= end_key:
        period_key = f"{year:04d}-{month:02d}"
        existing = by_key.get(period_key)
        if existing is not None:
            out.append(existing)
        else:
            out.append(
                MonthlyDeposit(
                    period=date(year, month, 1),
                    label=f"{calendar.month_name[month]} {year}",
                    deposit_eur=0.0,
                    deposit_usd=0.0,
                    portfolio_eur=0.0,
                    sort_order=sort_order,
                )
            )
        month += 1
        if month > 12:
            month = 1
            year += 1
        sort_order += 1
    return out


def valuation_as_of(deposit_period: date, *, reference: date | None = None) -> date:
    """Last date to use for month-end marks (today when valuing the current month)."""
    today = reference or date.today()
    end = month_end(deposit_period)
    if deposit_period.year == today.year and deposit_period.month == today.month:
        return min(today, end)
    return end


def fx_rates_carry_forward(
    deposits: list[MonthlyDeposit],
    *,
    default_fx: float = 0.92,
) -> dict[str, float]:
    """Map each deposit month to EUR/USD using deposit-implied rates (legacy helper)."""
    running = default_fx
    rates: dict[str, float] = {}
    for deposit in deposits:
        if deposit.deposit_eur > 0 and deposit.deposit_usd > 0:
            running = deposit.deposit_eur / deposit.deposit_usd
        rates[deposit.period_key] = running
    return rates


def fx_eur_per_usd_by_month(
    deposits: list[MonthlyDeposit],
    *,
    reference: date | None = None,
) -> dict[str, float]:
    """EUR-per-USD for each month using the FX rate on that month's valuation date."""
    from services.fx_rate_service import load_eur_usd_market_series, resolve_eur_per_usd

    today = reference or date.today()
    market_series = load_eur_usd_market_series()
    rates: dict[str, float] = {}
    for deposit in deposits:
        as_of = valuation_as_of(deposit.period, reference=today)
        rates[deposit.period_key] = resolve_eur_per_usd(
            as_of,
            deposits,
            market_series=market_series,
        )
    return rates


def shares_from_records(records: list[PurchaseRecord], as_of: date) -> float:
    """Share balance on ``as_of`` from explicit journal buy/sell rows."""
    if not records:
        return 0.0
    if not any(record.shares is not None and record.shares > 0 for record in records):
        return 0.0

    total = 0.0
    for record in sorted(records, key=lambda item: item.purchase_date):
        if record.purchase_date > as_of:
            continue
        if record.shares is None or record.shares <= 0:
            continue
        delta = float(record.shares)
        if record.side == "sell":
            delta = -delta
        total += delta
    return max(total, 0.0)


def journal_mark_price(records: list[PurchaseRecord], as_of: date) -> float | None:
    """Last trade price on or before ``as_of`` — fallback when library history is missing."""
    price: float | None = None
    for record in sorted(records, key=lambda item: item.purchase_date):
        if record.purchase_date > as_of:
            break
        if record.price_usd > 0:
            price = float(record.price_usd)
    return price


def _usable_month_valuation(valuation: MonthPortfolioValuation | None) -> bool:
    """True when a computed mark is good enough to show or persist."""
    if valuation is None or valuation.portfolio_eur <= 0 or valuation.symbols_priced <= 0:
        return False
    # Full coverage is ideal; allow partial books when most held symbols are priced.
    return valuation.coverage >= 0.5


def _last_bar_date_on_or_before(series: list[tuple[date, float]], as_of: date) -> date | None:
    last: date | None = None
    for point_date, _close in series:
        if point_date <= as_of:
            last = point_date
        else:
            break
    return last


def _close_on_or_before(series: list[tuple[date, float]], as_of: date) -> float | None:
    """Latest available close on or before ``as_of``."""
    if not series:
        return None
    best: float | None = None
    for point_date, close in series:
        if point_date <= as_of:
            best = close
        else:
            break
    return best


def _close_for_month_end(series: list[tuple[date, float]], as_of: date) -> float | None:
    """
    Month-end mark: prefer the last in-month close on or before ``as_of``,
    else the latest prior close.
    """
    if not series:
        return None
    year, month = as_of.year, as_of.month
    in_month: float | None = None
    for point_date, close in series:
        if point_date > as_of:
            break
        if point_date.year == year and point_date.month == month:
            in_month = close
    if in_month is not None:
        return in_month
    return _close_on_or_before(series, as_of)


def _mark_price_for_date(
    series: list[tuple[date, float]],
    as_of: date,
    *,
    snapshot_price: float | None = None,
    fallback_price: float | None = None,
    live_price: float | None = None,
    reference: date | None = None,
) -> float | None:
    """
    Month-end mark: last in-month close on or before ``as_of``, else latest prior close.

    When library history is missing, use the latest journal trade price on or before
    ``as_of``, then the document snapshot price. Live quotes are ignored.
    """
    _ = live_price, reference
    history_close = _close_for_month_end(series, as_of)
    if history_close is not None:
        return history_close
    if fallback_price is not None and fallback_price > 0:
        return fallback_price
    if snapshot_price is not None and snapshot_price > 0:
        return snapshot_price
    return None


def _price_series(document: Any) -> list[tuple[date, float]]:
    if document is None:
        return []
    history = getattr(document, "price_history", None) or []
    points: list[tuple[date, float]] = []
    for point in history:
        point_date = getattr(point, "date", None)
        if point_date is None:
            continue
        close = getattr(point, "adjusted_close", None)
        if close in (None, 0):
            close = getattr(point, "close", None)
        try:
            value = float(close)
        except (TypeError, ValueError):
            continue
        if value > 0:
            points.append((point_date, value))
    points.sort(key=lambda item: item[0])
    return points


def _merge_price_series(
    primary: list[tuple[date, float]],
    secondary: list[tuple[date, float]],
) -> list[tuple[date, float]]:
    """Merge two histories; primary closes win on the same date."""
    by_date = dict(secondary)
    by_date.update(dict(primary))
    return sorted(by_date.items(), key=lambda item: item[0])


def _series_from_stooq(symbol: str) -> list[tuple[date, float]]:
    try:
        from data_ingestion.providers.stooq import StooqProvider

        snap = StooqProvider().fetch(symbol)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Stooq series unavailable for %s: %s", symbol, exc)
        return []
    if snap is None:
        return []
    return _price_series(
        type(
            "_Doc",
            (),
            {
                "price_history": snap.price_history,
                "current_price": snap.current_price,
            },
        )()
    )


def _series_from_yahoo(symbol: str) -> list[tuple[date, float]]:
    try:
        from utils.yfinance_history import fetch_price_history
    except ImportError:
        return []
    try:
        frame = fetch_price_history(symbol, years=15)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Yahoo series unavailable for %s: %s", symbol, exc)
        return []
    if frame is None or getattr(frame, "empty", True):
        return []
    points: list[tuple[date, float]] = []
    close_col = "Close" if "Close" in frame.columns else None
    if close_col is None and "Adj Close" in frame.columns:
        close_col = "Adj Close"
    if close_col is None:
        return []
    for index, row in frame.iterrows():
        try:
            if hasattr(index, "date"):
                point_date = index.date()
            else:
                point_date = date.fromisoformat(str(index)[:10])
            close = float(row[close_col])
        except (TypeError, ValueError, AttributeError):
            continue
        if close > 0:
            points.append((point_date, close))
    points.sort(key=lambda item: item[0])
    return points


def _fetch_remote_price_series(
    symbol: str,
    *,
    prefer: str = "stooq",
) -> tuple[list[tuple[date, float]], str]:
    """
    Fetch OHLCV from Stooq and/or Yahoo.

    Preference order is Stooq then Yahoo (or the reverse when ``prefer='yfinance'``).
    Results are cached in-process to avoid repeat network calls.
    """
    cached = _REMOTE_SERIES_CACHE.get(symbol)
    if cached is not None:
        return cached, "cache"

    order = ("stooq", "yfinance") if prefer == "stooq" else ("yfinance", "stooq")
    best: list[tuple[date, float]] = []
    best_source = "none"
    for source in order:
        series = _series_from_stooq(symbol) if source == "stooq" else _series_from_yahoo(symbol)
        if len(series) > len(best):
            best = series
            best_source = source
        if len(series) >= _MIN_LIBRARY_BARS:
            _REMOTE_SERIES_CACHE[symbol] = series
            return series, source
    if best:
        _REMOTE_SERIES_CACHE[symbol] = best
    return best, best_source


def _attach_and_hydrate_documents(documents: dict[str, Any]) -> dict[str, Any]:
    try:
        from db.connection import use_cloud_sql

        if use_cloud_sql():
            from db.postgres_market_history_store import PostgresMarketHistoryStore

            history_store = PostgresMarketHistoryStore()
            for symbol in list(documents):
                doc = documents.get(symbol)
                if doc is not None:
                    documents[symbol] = history_store.attach_history_to_document(doc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not attach Postgres price history: %s", exc)

    try:
        from utils.stock_document_history import hydrate_document_history

        for symbol in list(documents):
            doc = documents.get(symbol)
            if doc is not None:
                documents[symbol] = hydrate_document_history(doc)
    except ImportError:
        pass
    return documents


def _resolve_symbol_series(
    symbol: str,
    documents: dict[str, Any],
    *,
    fetch_remote: bool,
) -> tuple[list[tuple[date, float]], str, float | None]:
    """Return (series, source_label, snapshot_price) for one symbol."""
    sym = symbol.strip().upper()
    doc = documents.get(sym) or documents.get(symbol)
    series = _price_series(doc)
    if len(series) >= _MIN_LIBRARY_BARS:
        source = "library"
    elif series:
        source = "library-thin"
    else:
        source = "none"
    if fetch_remote and len(series) < _MIN_LIBRARY_BARS:
        remote, remote_source = _fetch_remote_price_series(sym)
        if remote:
            if series:
                series = _merge_price_series(series, remote)
                source = f"library+{remote_source}"
            else:
                series = remote
                source = remote_source
    snapshot = getattr(doc, "current_price", None) if doc is not None else None
    try:
        price = float(snapshot) if snapshot is not None else None
    except (TypeError, ValueError):
        price = None
    if (price is None or price <= 0) and series:
        price = series[-1][1]
    return series, source, price if price and price > 0 else None


def _load_price_series(
    symbols: list[str],
    *,
    fetch_remote: bool = False,
) -> tuple[dict[str, list[tuple[date, float]]], dict[str, float], dict[str, str]]:
    """
    Load month-end mark histories.

    Order: shared market library (+ Postgres history table) → optional Stooq/Yahoo
    gap-fill for thin or missing symbols.
    """
    if not symbols:
        return {}, {}, {}
    try:
        from services.shared_market_db import load_documents
    except ImportError:
        return {}, {}, {}

    documents = _attach_and_hydrate_documents(load_documents(symbols))
    series_out: dict[str, list[tuple[date, float]]] = {}
    snapshot_out: dict[str, float] = {}
    source_out: dict[str, str] = {}
    for symbol in symbols:
        series, source, snapshot = _resolve_symbol_series(
            symbol,
            documents,
            fetch_remote=fetch_remote,
        )
        sym = symbol.strip().upper()
        if series:
            series_out[sym] = series
            source_out[sym] = source
        if snapshot is not None:
            snapshot_out[sym] = snapshot
    return series_out, snapshot_out, source_out


def _classify_mark_source(
    *,
    used_history: bool,
    series_source: str,
    used_journal: bool,
) -> str:
    if used_history:
        if series_source.startswith("library"):
            return "library"
        if series_source in {"stooq", "yfinance", "cache"} or "+" in series_source:
            return "remote"
        return "library"
    if used_journal:
        return "journal"
    return "snapshot"


def _cross_check_month_marks(
    *,
    marks: dict[str, float],
    series_sources: dict[str, str],
    as_of: date,
    fetch_remote: bool,
) -> tuple[str, str, int, int]:
    """
    Compare primary month-end marks against an alternate free source.

    Returns ``(status, note, agreed, disagreed)``.
    """
    checkable = [
        symbol
        for symbol, source in series_sources.items()
        if symbol in marks and source not in {"none", "journal", "snapshot"}
    ]
    if not checkable:
        return "unchecked", "No market closes available to cross-check", 0, 0
    if not fetch_remote:
        return (
            "unchecked",
            f"{len(checkable)} market mark(s) from library/remote cache (cross-check on sync)",
            0,
            0,
        )

    agreed = 0
    disagreed = 0
    worst = 0.0
    samples: list[str] = []
    for symbol in checkable[:12]:
        primary = marks[symbol]
        primary_source = series_sources.get(symbol, "library")
        prefer = "yfinance" if "stooq" in primary_source else "stooq"
        alt_series, alt_source = _fetch_remote_price_series(symbol, prefer=prefer)
        if alt_source == "cache" and "stooq" in primary_source:
            # Force the other provider when cache already holds the primary fill.
            alt_series = (
                _series_from_yahoo(symbol) if prefer == "yfinance" else _series_from_stooq(symbol)
            )
            alt_source = prefer if alt_series else "none"
        alt_close = _close_for_month_end(alt_series, as_of)
        if alt_close is None or primary <= 0:
            continue
        rel = abs(alt_close - primary) / primary
        worst = max(worst, rel)
        if rel <= _PRICE_CROSSCHECK_TOLERANCE:
            agreed += 1
        else:
            disagreed += 1
            samples.append(f"{symbol} {rel:.1%}")

    checked = agreed + disagreed
    if checked == 0:
        return "unchecked", "Alternate source returned no overlapping closes", 0, 0
    if disagreed == 0:
        return (
            "ok",
            f"{agreed}/{checked} marks within {_PRICE_CROSSCHECK_TOLERANCE:.0%} of Stooq/Yahoo",
            agreed,
            disagreed,
        )
    if disagreed / checked <= 0.25:
        return (
            "warning",
            f"{disagreed}/{checked} mark(s) diverge >{_PRICE_CROSSCHECK_TOLERANCE:.0%}"
            + (f" ({', '.join(samples[:3])})" if samples else ""),
            agreed,
            disagreed,
        )
    return (
        "failed",
        f"{disagreed}/{checked} marks disagree with secondary source"
        + (f" ({', '.join(samples[:3])})" if samples else ""),
        agreed,
        disagreed,
    )


def _value_one_month(
    *,
    deposit: MonthlyDeposit,
    all_symbols: list[str],
    records_by_symbol: dict[str, list[PurchaseRecord]],
    price_series: dict[str, list[tuple[date, float]]],
    snapshot_prices: dict[str, float],
    series_sources: dict[str, str],
    fx: float,
    as_of: date,
    validation_target: str | None,
    fetch_remote: bool,
) -> MonthPortfolioValuation | None:
    total_usd = 0.0
    symbols_held = 0
    symbols_priced = 0
    library_priced = 0
    remote_priced = 0
    journal_priced = 0
    missing_symbols: list[str] = []
    month_marks: dict[str, float] = {}
    month_sources: dict[str, str] = {}

    for symbol in all_symbols:
        symbol_records = records_by_symbol.get(symbol, [])
        shares = shares_from_records(symbol_records, as_of)
        if shares <= 0:
            continue
        symbols_held += 1
        series = price_series.get(symbol, [])
        history_close = _close_for_month_end(series, as_of)
        journal_price = journal_mark_price(symbol_records, as_of)
        close = _mark_price_for_date(
            series,
            as_of,
            snapshot_price=snapshot_prices.get(symbol),
            fallback_price=journal_price,
        )
        if close is None:
            missing_symbols.append(symbol)
            continue
        total_usd += shares * close
        symbols_priced += 1
        used_history = history_close is not None
        used_journal = (
            (not used_history) and journal_price is not None and abs(close - journal_price) < 1e-9
        )
        mark_source = _classify_mark_source(
            used_history=used_history,
            series_source=series_sources.get(symbol, "none"),
            used_journal=used_journal,
        )
        if mark_source == "library":
            library_priced += 1
        elif mark_source == "remote":
            remote_priced += 1
        elif mark_source == "journal":
            journal_priced += 1
        month_marks[symbol] = close
        month_sources[symbol] = series_sources.get(symbol, mark_source)

    if total_usd <= 0 or symbols_held == 0:
        return None

    if missing_symbols:
        logger.debug(
            "Month %s missing closes for: %s",
            deposit.period_key,
            ", ".join(missing_symbols[:8]) + ("…" if len(missing_symbols) > 8 else ""),
        )

    validation_status = "unchecked"
    validation_note = ""
    if deposit.period_key == validation_target:
        validation_status, validation_note, _ok, _bad = _cross_check_month_marks(
            marks=month_marks,
            series_sources=month_sources,
            as_of=as_of,
            fetch_remote=fetch_remote,
        )

    return MonthPortfolioValuation(
        portfolio_usd=round(total_usd, 2),
        portfolio_eur=round(total_usd * fx, 2),
        symbols_held=symbols_held,
        symbols_priced=symbols_priced,
        library_priced=library_priced,
        remote_priced=remote_priced,
        journal_priced=journal_priced,
        validation_status=validation_status,
        validation_note=validation_note,
    )


def compute_monthly_portfolio_valuations(
    deposits: list[MonthlyDeposit],
    *,
    db_path: Path | None = None,
    journal_service: PortfolioPurchaseJournalService | None = None,
    fetch_remote: bool = False,
) -> dict[str, MonthPortfolioValuation]:
    """
    Estimate end-of-month portfolio value from journal share counts and market closes.

    Price priority per holding: market library → Stooq/Yahoo gap-fill (when enabled) →
    last journal trade → document snapshot. Optional cross-check validates marks against
    a second free source during remote sync.
    """
    if not deposits:
        return {}

    if journal_service is not None:
        js = journal_service
    elif db_path is None:
        js = PortfolioPurchaseJournalService()
    else:
        js = PortfolioPurchaseJournalService(
            journal_store=PurchaseJournalStore(db_path=db_path, seed=False),
            portfolio_store=PortfolioStore(db_path=db_path, seed=False),
        )
    records = js.journal.list_purchases(portfolio_only=False)
    open_holdings = {
        holding.symbol.strip().upper(): holding
        for holding in js.portfolio.list_open_holdings()
        if holding.shares > 0
    }
    if not records and not open_holdings:
        return {}

    records_by_symbol: dict[str, list[PurchaseRecord]] = {}
    for record in records:
        sym = record.symbol.strip().upper()
        records_by_symbol.setdefault(sym, []).append(record)

    all_symbols = sorted(set(records_by_symbol) | set(open_holdings))
    price_series, snapshot_prices, series_sources = _load_price_series(
        all_symbols,
        fetch_remote=fetch_remote,
    )
    today = date.today()
    fx_by_month = fx_eur_per_usd_by_month(deposits, reference=today)
    values: dict[str, MonthPortfolioValuation] = {}

    validation_target = None
    for deposit in reversed(deposits):
        if valuation_as_of(deposit.period, reference=today) < today:
            validation_target = deposit.period_key
            break

    for deposit in deposits:
        valued = _value_one_month(
            deposit=deposit,
            all_symbols=all_symbols,
            records_by_symbol=records_by_symbol,
            price_series=price_series,
            snapshot_prices=snapshot_prices,
            series_sources=series_sources,
            fx=fx_by_month.get(deposit.period_key, 0.92),
            as_of=valuation_as_of(deposit.period, reference=today),
            validation_target=validation_target,
            fetch_remote=fetch_remote,
        )
        if valued is not None:
            values[deposit.period_key] = valued

    return values


def summarize_valuation_quality(
    valuations: dict[str, MonthPortfolioValuation],
) -> ValuationQualityReport:
    """Aggregate mark-source and cross-check status for UI captions."""
    if not valuations:
        return ValuationQualityReport(0, 0, 0, 0, 0, 0, 0, "No month-end marks computed")

    months = list(valuations.values())
    full = sum(1 for item in months if item.coverage >= 1.0)
    validated = sum(1 for item in months if item.validation_status == "ok")
    warnings = sum(1 for item in months if item.validation_status in {"warning", "failed"})
    library = sum(item.library_priced for item in months)
    remote = sum(item.remote_priced for item in months)
    journal = sum(item.journal_priced for item in months)
    notes = [item.validation_note for item in months if item.validation_note]
    note = (
        notes[-1]
        if notes
        else (
            f"{full}/{len(months)} months fully priced"
            + (f"; {journal} trade-price fallback marks" if journal else "")
        )
    )
    return ValuationQualityReport(
        months_valued=len(months),
        months_full_coverage=full,
        months_validated_ok=validated,
        months_with_warnings=warnings,
        library_marks=library,
        remote_marks=remote,
        journal_marks=journal,
        note=note,
    )


def portfolio_eur_to_store(
    *,
    stored: float | None,
    valuation: MonthPortfolioValuation | None,
) -> float | None:
    """
    Decide the portfolio € to persist on ``monthly_deposits``.

    Journal marks (shares × month-end closes, with trade-price fallback) are saved
    for every month that can be priced. Broker NAV is kept only when marks fail.
    """
    if _usable_month_valuation(valuation):
        assert valuation is not None
        return valuation.portfolio_eur
    if stored is not None and stored > 0:
        return stored
    return None


def compute_monthly_portfolio_eur(
    deposits: list[MonthlyDeposit],
    *,
    db_path: Path | None = None,
) -> dict[str, float]:
    """Backward-compatible EUR map for callers that only need the amount."""
    return {
        key: value.portfolio_eur
        for key, value in compute_monthly_portfolio_valuations(deposits, db_path=db_path).items()
    }


def pick_portfolio_eur_for_month(
    *,
    stored: float | None,
    valuation: MonthPortfolioValuation | None,
) -> float | None:
    """
    Portfolio € for evolution charts, KPIs, and monthly detail tables.

    Prefer persisted month-end values. When a month has no stored value, use the
    computed journal mark (including trade-price fallbacks).
    """
    if stored is not None and stored > 0:
        return stored
    if _usable_month_valuation(valuation):
        assert valuation is not None
        return valuation.portfolio_eur
    return None
