"""
Build evidence rows for data sources and history intervals (no Streamlit).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from config import DATA_SOURCES, MAX_HISTORY_YEARS

Row = tuple[str, str]


def fmt_date(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return value.strftime("%Y-%m-%d")


def fmt_range(start: date | None, end: date | None, count: int) -> str:
    if count <= 0:
        return "No records in analysed library"
    if start and end:
        return f"{fmt_date(start)} → {fmt_date(end)} ({count:,} records)"
    return f"{count:,} records"


def price_history_bounds(doc: Any) -> tuple[date | None, date | None, int]:
    history = getattr(doc, "price_history", None) or []
    if not history:
        return None, None, 0
    dates = sorted(record.date for record in history if getattr(record, "date", None))
    if not dates:
        return None, None, 0
    return dates[0], dates[-1], len(dates)


def dividend_history_bounds(doc: Any) -> tuple[date | None, date | None, int]:
    history = getattr(doc, "dividend_history", None) or []
    if not history:
        return None, None, 0
    dates = sorted(record.ex_date for record in history if getattr(record, "ex_date", None))
    if not dates:
        return None, None, 0
    return dates[0], dates[-1], len(dates)


def yield_channel_bounds(channel: Any) -> tuple[date | None, date | None, int]:
    raw_dates = getattr(channel, "dates", None) or []
    if not raw_dates:
        return None, None, 0
    parsed: list[date] = []
    for item in raw_dates:
        if isinstance(item, datetime):
            parsed.append(item.date())
        elif isinstance(item, date):
            parsed.append(item)
    if not parsed:
        return None, None, 0
    parsed.sort()
    return parsed[0], parsed[-1], len(parsed)


def build_evidence_rows(
    symbol: str,
    *,
    data: Any = None,
    vector_doc: Any = None,
    yield_channel_data: Any = None,
    portfolio_prices_at: datetime | None = None,
) -> list[Row]:
    """Build (aspect, detail) rows describing data behind an analysis view."""
    rows: list[Row] = []
    symbol = (symbol or "").upper()

    rows.append(("Ticker", symbol or "—"))

    if portfolio_prices_at:
        rows.append(
            (
                "Portfolio price snapshot",
                f"{fmt_date(portfolio_prices_at)} (your holdings table & P/L)",
            )
        )
    else:
        rows.append(
            (
                "Portfolio price snapshot",
                "Not loaded — use **Reload live data** in the sidebar",
            )
        )

    doc_updated = getattr(vector_doc, "last_updated", None) if vector_doc else None
    doc_source = getattr(getattr(vector_doc, "source", None), "value", None) if vector_doc else None
    if vector_doc:
        rows.append(
            (
                "Analysed stock library record",
                f"Updated {fmt_date(doc_updated)} · source {doc_source or 'unknown'}",
            )
        )
        p_start, p_end, p_count = price_history_bounds(vector_doc)
        rows.append(("Price history interval", fmt_range(p_start, p_end, p_count)))
        d_start, d_end, d_count = dividend_history_bounds(vector_doc)
        rows.append(("Dividend payment history interval", fmt_range(d_start, d_end, d_count)))
        if data is not None:
            yield_source = getattr(data, "_yield_source", None)
            if yield_source:
                rows.append(("Dividend yield source", str(yield_source)))
    else:
        rows.append(
            (
                "Analysed stock library",
                f"No stored history for **{symbol}** — run ingest/enrich for this ticker",
            )
        )

    stock_updated = getattr(data, "_last_updated", None) if data else None
    quality = getattr(data, "data_quality_score", None) if data else None
    used_sources = getattr(data, "data_sources", None) if data else None
    if data:
        source_text = ", ".join(used_sources) if used_sources else DATA_SOURCES["primary"]
        quality_text = f"{quality:.0f}%" if quality is not None else "n/a"
        rows.append(
            (
                "Fundamentals snapshot",
                f"Updated {fmt_date(stock_updated)} · quality {quality_text} · {source_text}",
            )
        )

    if yield_channel_data:
        years = getattr(yield_channel_data, "years_analyzed", None) or MAX_HISTORY_YEARS
        points = getattr(yield_channel_data, "data_points", 0) or 0
        y_start, y_end, y_count = yield_channel_bounds(yield_channel_data)
        interval = fmt_range(y_start, y_end, y_count or points)
        rows.append(("Yield channel analysis window", f"Last {years} years · {interval}"))
        y10 = getattr(yield_channel_data, "yield_10th", None)
        y90 = getattr(yield_channel_data, "yield_90th", None)
        if y10 is not None and y90 is not None:
            zone_detail = f"Weiss-style percentile bands ({y10:.2f}%-{y90:.2f}% historical yield)"
        else:
            zone_detail = "Weiss-style percentile bands on historical yield"
        rows.append(("Yield zone method", zone_detail))
    else:
        rows.append(
            (
                "Yield channel analysis window",
                f"Not preloaded — chart uses up to {MAX_HISTORY_YEARS} years when available",
            )
        )

    rows.append(
        (
            "History storage cap",
            f"Analysed library keeps up to {MAX_HISTORY_YEARS} years of price & dividend series",
        )
    )
    rows.append(("Live market fields", DATA_SOURCES["primary"]))
    rows.append(("Fundamentals & ratios", DATA_SOURCES["fundamentals"]))
    rows.append(("Dividend & price trends", DATA_SOURCES["historical"]))
    rows.append(("Analyst consensus (if shown)", DATA_SOURCES["analyst"]))
    rows.append(
        (
            "What scores & watchlists use",
            "Stored history intervals above + latest reload for prices, payout, "
            "streak, and yield zones",
        )
    )
    return rows


def build_portfolio_session_rows(
    *,
    loaded_at: datetime | None,
    holding_count: int,
    charts_ready: int = 0,
    library_ready: int = 0,
) -> list[Row]:
    """Portfolio-wide data snapshot (sidebar / holdings header)."""
    return [
        ("Holdings in session", f"{holding_count}"),
        (
            "Last portfolio reload",
            fmt_date(loaded_at) if loaded_at else "Not loaded yet",
        ),
        (
            "Preloaded yield charts",
            f"{charts_ready} of {holding_count} holdings" if holding_count else "—",
        ),
        (
            "Analysed library matches",
            f"{library_ready} of {holding_count} holdings have stored history"
            if holding_count
            else "—",
        ),
        (
            "Analysis history cap",
            f"Up to {MAX_HISTORY_YEARS} years per ticker in analysed stocks",
        ),
    ]
