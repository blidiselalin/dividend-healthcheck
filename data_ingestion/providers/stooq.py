"""
Stooq provider — daily OHLCV history via public CSV (free, no API key).

US symbols use ``{ticker}.us`` (e.g. ``ko.us``). Fills price and history when
Yahoo history is empty.

Docs: https://stooq.com/db/h/
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from typing import List, Optional

from data_ingestion.base import BaseFetcher
from data_ingestion.models import DataSource, PriceHistory
from data_ingestion.providers._numeric import as_float
from data_ingestion.providers.base import StockDataProvider
from data_ingestion.providers.snapshot import StockSnapshot

logger = logging.getLogger(__name__)

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"


class StooqProvider(BaseFetcher, StockDataProvider):
    source = DataSource.STOOQ
    field_groups = frozenset({"price", "history", "performance"})
    priority = 25

    def available(self) -> bool:
        return bool(self.session)

    def fetch(self, symbol: str) -> Optional[StockSnapshot]:
        if not self.available():
            return None

        symbol = symbol.upper().strip()
        stooq_symbol = _stooq_symbol(symbol)
        self._rate_limit()
        rows = self._fetch_csv(stooq_symbol)
        if not rows:
            return None

        snap = StockSnapshot(symbol=symbol, source=self.source)
        snap.price_history = rows[-2520:]
        if rows:
            last = rows[-1]
            snap.current_price = last.close
            snap.fifty_two_week_high = max(point.high for point in rows[-252:])
            snap.fifty_two_week_low = min(point.low for point in rows[-252:])
            if len(rows) >= 252:
                year_ago = rows[-252].close
                if year_ago > 0:
                    snap.price_return_1y = ((last.close / year_ago) - 1) * 100

        return snap

    def _fetch_csv(self, stooq_symbol: str) -> List[PriceHistory]:
        if not self.session:
            return []
        try:
            response = self.session.get(
                STOOQ_DAILY_URL.format(symbol=stooq_symbol),
                timeout=25,
            )
            response.raise_for_status()
            text = response.text.strip()
            if not text or text.lower().startswith("<!doctype"):
                return []
            return _parse_stooq_csv(text)
        except Exception as exc:
            logger.debug("Stooq fetch failed for %s: %s", stooq_symbol, exc)
            return []


def _stooq_symbol(symbol: str) -> str:
    """Map US ticker to Stooq symbol (e.g. BRK.B → brk-b.us)."""
    normalized = symbol.lower().replace(".", "-")
    return f"{normalized}.us"


def _parse_stooq_csv(text: str) -> List[PriceHistory]:
    reader = csv.DictReader(io.StringIO(text))
    points: List[PriceHistory] = []
    for row in reader:
        try:
            row_date = datetime.strptime(row["Date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        close = as_float(row.get("Close"))
        if close is None:
            continue
        points.append(
            PriceHistory(
                date=row_date,
                open=as_float(row.get("Open")) or close,
                high=as_float(row.get("High")) or close,
                low=as_float(row.get("Low")) or close,
                close=close,
                volume=int(as_float(row.get("Volume")) or 0),
                adjusted_close=close,
            )
        )
    points.sort(key=lambda point: point.date)
    return points
