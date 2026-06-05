"""
Reliable yfinance price history fetch with fallbacks and quiet failures.

Yahoo sometimes returns empty frames for period=10y while start/end works.
We also fall back to analysed-stock price_history when the API fails.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

try:
    import pandas as pd
    import yfinance as yf

    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    pd = None  # type: ignore
    yf = None  # type: ignore


@contextmanager
def suppress_yfinance_noise():
    """Hide yfinance 'possibly delisted' noise on empty history responses."""
    import logging

    names = ("yfinance", "urllib3", "peewee", "yfinance.base", "yfinance.scrapers")
    previous: List[tuple] = []
    for name in names:
        log = logging.getLogger(name)
        previous.append((log, log.level))
        log.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        for log, level in previous:
            log.setLevel(level)


def _history_kwargs() -> dict:
    """Extra kwargs supported by the installed yfinance version."""
    return {"auto_adjust": True, "actions": True}


def _call_history(ticker: Any, **kwargs) -> Any:
    """Call Ticker.history, using repair= when supported."""
    try:
        return ticker.history(repair=True, **kwargs)
    except TypeError:
        return ticker.history(**kwargs)


def fetch_price_history(
    symbol: str,
    *,
    years: Optional[int] = 10,
    period: Optional[str] = None,
) -> "pd.DataFrame":
    """
    Fetch OHLCV history for a symbol.

    Tries period strings, then explicit start/end, then shorter windows.
    Returns an empty DataFrame on failure (no console spam).
    """
    if not YFINANCE_AVAILABLE:
        return pd.DataFrame()

    from data_ingestion.sp500_universe import yahoo_ticker

    sym = yahoo_ticker(symbol)
    ticker = yf.Ticker(sym)
    base_kw = _history_kwargs()

    periods: List[str] = []
    if period:
        periods.append(period)
    elif years:
        periods.extend([f"{years}y", "5y", "2y", "1y", "max"])
    else:
        periods.append("max")

    with suppress_yfinance_noise():
        for p in periods:
            try:
                frame = _call_history(ticker, period=p, **base_kw)
                if frame is not None and not frame.empty:
                    return frame
            except Exception as exc:
                logger.debug("%s history period=%s failed: %s", sym, p, exc)

        if years:
            end = date.today() + timedelta(days=1)
            start = date.today() - timedelta(days=years * 365 + 60)
            try:
                frame = _call_history(
                    ticker,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    **base_kw,
                )
                if frame is not None and not frame.empty:
                    return frame
            except Exception as exc:
                logger.debug("%s history start/end failed: %s", sym, exc)

    return pd.DataFrame()


def history_dataframe_from_document(
    doc: Any,
    *,
    years: int = 10,
    min_rows: int = 100,
) -> "pd.DataFrame":
    """Build a price history DataFrame from analysed-stock library records."""
    if not YFINANCE_AVAILABLE or doc is None:
        return pd.DataFrame()

    price_history = getattr(doc, "price_history", None) or []
    if not price_history:
        return pd.DataFrame()

    cutoff = date.today() - timedelta(days=years * 365 + 30)
    rows = [p for p in price_history if getattr(p, "date", None) and p.date >= cutoff]
    if len(rows) < min_rows:
        rows = sorted(price_history, key=lambda p: p.date)

    if not rows:
        return pd.DataFrame()

    records = []
    index = []
    for point in rows:
        d = point.date
        close = float(
            getattr(point, "adjusted_close", None)
            or getattr(point, "close", None)
            or 0
        )
        if close <= 0:
            continue
        index.append(pd.Timestamp(d))
        records.append(
            {
                "Open": float(getattr(point, "open", close) or close),
                "High": float(getattr(point, "high", close) or close),
                "Low": float(getattr(point, "low", close) or close),
                "Close": close,
                "Adj Close": close,
                "Volume": int(getattr(point, "volume", 0) or 0),
                "Dividends": 0.0,
            }
        )

    if len(records) < min_rows:
        return pd.DataFrame()

    frame = pd.DataFrame(records, index=index)
    frame.sort_index(inplace=True)
    return frame


def fetch_price_history_with_fallback(
    symbol: str,
    *,
    years: int = 10,
    document: Any = None,
    min_rows: int = 100,
    prefer_library: bool = False,
) -> tuple["pd.DataFrame", str]:
    """
    Fetch OHLCV history from yfinance and/or analysed-stock price_history.

    When ``prefer_library`` is True and the document has enough rows, use the
    shared library first so prices align with stored dividend_history.

    Returns (dataframe, source_label): 'yfinance', 'analysed_library', or 'none'.
    """
    if prefer_library and document is not None:
        library = history_dataframe_from_document(
            document, years=years, min_rows=min_rows
        )
        if library is not None and not library.empty and len(library) >= min_rows:
            logger.debug(
                "%s: using analysed-library price history (%d rows)",
                symbol,
                len(library),
            )
            return library, "analysed_library"

    frame = fetch_price_history(symbol, years=years)
    if frame is not None and not frame.empty and len(frame) >= min_rows:
        return frame, "yfinance"

    if document is not None:
        library = history_dataframe_from_document(
            document, years=years, min_rows=min_rows
        )
        if library is not None and not library.empty:
            logger.info(
                "%s: using analysed-library price history (%d rows) after yfinance miss",
                symbol,
                len(library),
            )
            return library, "analysed_library"

    return pd.DataFrame(), "none"


def dividend_series_from_records(records: Any) -> "pd.Series":
    """Cash dividends indexed by ex-date from library DividendRecord rows."""
    if not YFINANCE_AVAILABLE or not records:
        return pd.Series(dtype=float)

    totals: dict = {}
    for div in records:
        ex_raw = None
        amount = None
        if isinstance(div, dict):
            ex_raw = div.get("ex_date")
            amount = div.get("amount")
        elif hasattr(div, "ex_date") and hasattr(div, "amount"):
            ex_raw = div.ex_date
            amount = div.amount
        if ex_raw is None or amount is None:
            continue
        try:
            if isinstance(ex_raw, str):
                ex_date = date.fromisoformat(ex_raw[:10])
            elif isinstance(ex_raw, date):
                ex_date = ex_raw
            elif hasattr(ex_raw, "date"):
                ex_date = ex_raw.date()
            else:
                continue
            value = float(amount)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        key = pd.Timestamp(ex_date)
        totals[key] = totals.get(key, 0.0) + value

    if not totals:
        return pd.Series(dtype=float)
    return pd.Series(totals).sort_index()


def dividend_series_from_document(document: Any, *, years: int = 10) -> "pd.Series":
    """Dividend payments from a StockDocument (history, else yield metadata estimate)."""
    if document is None:
        return pd.Series(dtype=float)

    history = getattr(document, "dividend_history", None) or []
    if len(history) >= 3:
        return dividend_series_from_records(history)

    price = getattr(document, "current_price", None)
    div_yield = getattr(document, "dividend_yield", None)
    try:
        price_f = float(price) if price is not None else 0.0
        yield_f = float(div_yield) if div_yield is not None else 0.0
    except (TypeError, ValueError):
        return pd.Series(dtype=float)
    if price_f <= 0 or yield_f <= 0:
        return pd.Series(dtype=float)

    quarterly = price_f * (yield_f / 100.0) / 4.0
    if quarterly <= 0:
        return pd.Series(dtype=float)

    today = date.today()
    payments: dict = {}
    for quarter in range(years * 4):
        month = today.month - (quarter * 3)
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        try:
            pay_date = date(year, month, 15)
        except ValueError:
            pay_date = date(year, month, 28)
        payments[pd.Timestamp(pay_date)] = quarterly
    return pd.Series(payments).sort_index()


def merge_dividend_series(*series: "pd.Series") -> "pd.Series":
    """Combine payment series without double-counting the same ex-date."""
    frames = [s for s in series if s is not None and not s.empty]
    if not frames:
        return pd.Series(dtype=float)
    combined = pd.concat(frames)
    combined.index = _to_naive_datetime_index(combined.index)
    return combined.groupby(level=0).max().sort_index()


def compute_ttm_from_payment_series(
    hist: "pd.DataFrame",
    payment_series: "pd.Series",
    *,
    min_rows: int = 60,
) -> Optional["pd.DataFrame"]:
    """
    Trailing 12-month dividend at each price date from ex-date payments.

    More reliable than rolling sparse daily Dividends columns (e.g. INTU, newer payers).
    """
    if not YFINANCE_AVAILABLE or hist is None or hist.empty or payment_series is None:
        return None
    if payment_series.empty:
        return None

    frame = hist.copy()
    frame.index = _to_naive_datetime_index(frame.index)
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame = frame.dropna(subset=["Close"])
    frame = frame[frame["Close"] > 0]
    if frame.empty:
        return None

    payments = payment_series.copy()
    payments.index = _to_naive_datetime_index(payments.index)
    payments = payments.astype(float)
    payments = payments[payments > 0].sort_index()
    if payments.empty:
        return None

    ttm_values = []
    for ts in frame.index:
        start = ts - pd.Timedelta(days=365)
        window = payments[(payments.index > start) & (payments.index <= ts)]
        ttm_values.append(float(window.sum()))

    frame["Div_TTM"] = ttm_values
    frame = frame[frame["Div_TTM"] > 0]
    return frame if len(frame) >= min_rows else None


def fetch_dividend_series(symbol: str) -> "pd.Series":
    """
    Cash dividend payments indexed by ex-date (empty Series on failure).
    """
    if not YFINANCE_AVAILABLE:
        return pd.Series(dtype=float)

    from data_ingestion.sp500_universe import yahoo_ticker

    sym = yahoo_ticker(symbol)
    ticker = yf.Ticker(sym)
    with suppress_yfinance_noise():
        try:
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                cleaned = divs[divs > 0].astype(float)
                if not cleaned.empty:
                    return cleaned.sort_index()
        except Exception as exc:
            logger.debug("%s ticker.dividends failed: %s", sym, exc)

        frame = fetch_price_history(sym, years=10)
        if frame is not None and not frame.empty and "Dividends" in frame.columns:
            payments = frame["Dividends"]
            payments = payments[payments > 0].astype(float)
            if not payments.empty:
                return payments.sort_index()

    return pd.Series(dtype=float)


def _to_naive_datetime_index(index: Any) -> "pd.DatetimeIndex":
    """Normalize index for merge (strip timezones, sort)."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.sort_values()


def align_dividends_to_price_index(
    hist: "pd.DataFrame",
    dividend_series: "pd.Series",
) -> "pd.DataFrame":
    """
    Map each dividend to the first trading day on or after its ex-date.

    Works for analysed-library price rows (no embedded dividends) and yfinance OHLCV.
    """
    if not YFINANCE_AVAILABLE or hist is None or hist.empty:
        return hist
    if dividend_series is None or dividend_series.empty:
        return hist

    frame = hist.copy()
    frame.index = _to_naive_datetime_index(frame.index)
    if "Dividends" not in frame.columns:
        frame["Dividends"] = 0.0
    payments = pd.to_numeric(frame["Dividends"], errors="coerce").fillna(0.0)

    divs = dividend_series.copy()
    divs.index = _to_naive_datetime_index(divs.index)
    divs = divs.astype(float)
    divs = divs[divs > 0]
    if divs.empty:
        return frame
    divs = divs.groupby(level=0).sum().sort_index()

    for ex, amount in divs.items():
        try:
            value = float(amount)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        ex_ts = pd.Timestamp(ex).normalize()
        position = payments.index.searchsorted(ex_ts, side="left")
        if position >= len(payments):
            continue
        target = payments.index[position]
        payments.loc[target] = float(payments.loc[target]) + value

    frame["Dividends"] = payments
    return frame
