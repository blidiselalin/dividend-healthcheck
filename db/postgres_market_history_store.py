"""
Normalized PostgreSQL storage for price/dividend time series (yield charts, exposure).

Separate from ``stock_documents`` aggregated JSONB — mirrors legacy Chroma
``price_history`` / ``dividend_history`` fields.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


class PostgresMarketHistoryStore:
    """Read/write ``stock_price_history`` and ``stock_dividend_history``."""

    def upsert_document_history(self, document: Any, *, conn: Any = None) -> None:
        """Persist in-memory history arrays for one symbol."""
        from db.connection import ensure_schema, get_connection

        symbol = (getattr(document, "symbol", None) or "").upper()
        if not symbol:
            return

        prices = getattr(document, "price_history", None) or []
        dividends = getattr(document, "dividend_history", None) or []
        if not prices and not dividends:
            return

        ensure_schema()
        if conn is not None:
            self._upsert(symbol, prices, dividends, conn)
            return

        with get_connection() as connection:
            self._upsert(symbol, prices, dividends, connection)

    def _upsert(
        self,
        symbol: str,
        prices: Sequence[Any],
        dividends: Sequence[Any],
        conn: Any,
    ) -> None:
        if prices:
            conn.execute("DELETE FROM stock_price_history WHERE symbol = %s", (symbol,))
            for point in prices:
                price_date = _parse_date(getattr(point, "date", None))
                if price_date is None:
                    continue
                close = getattr(point, "close", None)
                if close is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO stock_price_history (
                      symbol, price_date, open, high, low, close, adjusted_close, volume
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, price_date) DO UPDATE SET
                      open = EXCLUDED.open,
                      high = EXCLUDED.high,
                      low = EXCLUDED.low,
                      close = EXCLUDED.close,
                      adjusted_close = EXCLUDED.adjusted_close,
                      volume = EXCLUDED.volume
                    """,
                    (
                        symbol,
                        price_date,
                        getattr(point, "open", None),
                        getattr(point, "high", None),
                        getattr(point, "low", None),
                        float(close),
                        getattr(point, "adjusted_close", None),
                        getattr(point, "volume", None),
                    ),
                )

        if dividends:
            conn.execute("DELETE FROM stock_dividend_history WHERE symbol = %s", (symbol,))
            for record in dividends:
                ex_date = _parse_date(getattr(record, "ex_date", None))
                amount = getattr(record, "amount", None)
                if ex_date is None or amount is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO stock_dividend_history (
                      symbol, ex_date, amount, payment_date, frequency
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, ex_date) DO UPDATE SET
                      amount = EXCLUDED.amount,
                      payment_date = EXCLUDED.payment_date,
                      frequency = EXCLUDED.frequency
                    """,
                    (
                        symbol,
                        ex_date,
                        float(amount),
                        _parse_date(getattr(record, "payment_date", None)),
                        getattr(record, "frequency", None),
                    ),
                )

    def load_price_history(self, symbol: str, *, conn: Any = None) -> List[Any]:
        from data_ingestion.models import PriceHistory
        from db.connection import ensure_schema, get_connection

        symbol = symbol.upper()
        ensure_schema()

        def _fetch(connection: Any) -> List[Any]:
            rows = connection.execute(
                """
                SELECT price_date, open, high, low, close, adjusted_close, volume
                FROM stock_price_history
                WHERE symbol = %s
                ORDER BY price_date DESC
                """,
                (symbol,),
            ).fetchall()
            out: List[PriceHistory] = []
            for row in rows:
                data = dict(row)
                out.append(
                    PriceHistory(
                        date=data["price_date"],
                        open=float(data["open"] or data["close"] or 0),
                        high=float(data["high"] or data["close"] or 0),
                        low=float(data["low"] or data["close"] or 0),
                        close=float(data["close"] or 0),
                        volume=int(data["volume"] or 0),
                        adjusted_close=data.get("adjusted_close"),
                    )
                )
            return out

        if conn is not None:
            return _fetch(conn)
        with get_connection() as connection:
            return _fetch(connection)

    def load_dividend_history(self, symbol: str, *, conn: Any = None) -> List[Any]:
        from data_ingestion.models import DividendRecord
        from db.connection import ensure_schema, get_connection

        symbol = symbol.upper()
        ensure_schema()

        def _fetch(connection: Any) -> List[Any]:
            rows = connection.execute(
                """
                SELECT ex_date, amount, payment_date, frequency
                FROM stock_dividend_history
                WHERE symbol = %s
                ORDER BY ex_date DESC
                """,
                (symbol,),
            ).fetchall()
            out: List[DividendRecord] = []
            for row in rows:
                data = dict(row)
                out.append(
                    DividendRecord(
                        ex_date=data["ex_date"],
                        payment_date=data.get("payment_date"),
                        amount=float(data["amount"]),
                        frequency=data.get("frequency") or "quarterly",
                    )
                )
            return out

        if conn is not None:
            return _fetch(conn)
        with get_connection() as connection:
            return _fetch(connection)

    def attach_history_to_document(self, document: Any, *, conn: Any = None) -> Any:
        """Load price/dividend series from normalized tables when available."""
        symbol = (getattr(document, "symbol", None) or "").upper()
        if not symbol:
            return document

        json_prices = getattr(document, "price_history", None) or []
        json_divs = getattr(document, "dividend_history", None) or []

        try:
            table_prices = self.load_price_history(symbol, conn=conn)
            table_divs = self.load_dividend_history(symbol, conn=conn)
        except Exception as exc:
            logger.debug("History table load failed for %s: %s", symbol, exc)
            return document

        if table_prices and self._prefer_table_prices(table_prices, json_prices):
            document.price_history = table_prices
        if table_divs and len(table_divs) >= len(json_divs):
            document.dividend_history = table_divs
        return document

    @staticmethod
    def _prefer_table_prices(table_prices: list, json_prices: list) -> bool:
        """Prefer normalized table OHLCV when JSONB rows are duplicate or thinner."""
        if not table_prices:
            return False
        if not json_prices:
            return True

        from utils.yfinance_history import library_prices_trustworthy, unique_price_dates

        class _PriceDoc:
            def __init__(self, prices: list) -> None:
                self.price_history = prices

        table_ok = library_prices_trustworthy(_PriceDoc(table_prices), min_unique=52)
        json_ok = library_prices_trustworthy(_PriceDoc(json_prices), min_unique=52)
        if table_ok and not json_ok:
            return True
        if table_ok and json_ok:
            return unique_price_dates(_PriceDoc(table_prices)) >= unique_price_dates(
                _PriceDoc(json_prices)
            )
        return len(table_prices) >= len(json_prices)

    def history_coverage_summary(self) -> Dict[str, int]:
        """Counts using normalized tables, falling back to JSONB when tables are empty."""
        from config import MIN_YIELD_DIVIDEND_PAYMENTS, MIN_YIELD_PRICE_POINTS
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        with get_connection() as conn:
            row = conn.execute(
                """
                WITH price_counts AS (
                  SELECT symbol, COUNT(*) AS n FROM stock_price_history GROUP BY symbol
                ),
                div_counts AS (
                  SELECT symbol, COUNT(*) AS n FROM stock_dividend_history GROUP BY symbol
                )
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (
                    WHERE GREATEST(
                      COALESCE(p.n, 0),
                      jsonb_array_length(COALESCE(s.document->'price_history', '[]'::jsonb))
                    ) >= %s
                    AND GREATEST(
                      COALESCE(d.n, 0),
                      jsonb_array_length(COALESCE(s.document->'dividend_history', '[]'::jsonb))
                    ) >= %s
                  ) AS yield_ready,
                  COUNT(*) FILTER (
                    WHERE GREATEST(
                      COALESCE(p.n, 0),
                      jsonb_array_length(COALESCE(s.document->'price_history', '[]'::jsonb))
                    ) < %s
                    OR GREATEST(
                      COALESCE(d.n, 0),
                      jsonb_array_length(COALESCE(s.document->'dividend_history', '[]'::jsonb))
                    ) < %s
                  ) AS thin_history
                FROM stock_documents s
                LEFT JOIN price_counts p ON p.symbol = s.symbol
                LEFT JOIN div_counts d ON d.symbol = s.symbol
                """,
                (
                    MIN_YIELD_PRICE_POINTS,
                    MIN_YIELD_DIVIDEND_PAYMENTS,
                    MIN_YIELD_PRICE_POINTS,
                    MIN_YIELD_DIVIDEND_PAYMENTS,
                ),
            ).fetchone()
        data = dict(row) if row else {}
        return {
            "total": int(data.get("total") or 0),
            "yield_ready": int(data.get("yield_ready") or 0),
            "thin_history": int(data.get("thin_history") or 0),
            "min_price_points": MIN_YIELD_PRICE_POINTS,
            "min_dividend_payments": MIN_YIELD_DIVIDEND_PAYMENTS,
        }

    def symbol_history_counts(self, symbol: str) -> Dict[str, int]:
        from db.connection import ensure_schema, get_connection

        symbol = symbol.upper()
        ensure_schema()
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM stock_price_history WHERE symbol = %s) AS price_points,
                  (SELECT COUNT(*) FROM stock_dividend_history WHERE symbol = %s) AS dividend_payments
                """,
                (symbol, symbol),
            ).fetchone()
        data = dict(row) if row else {}
        return {
            "price_points": int(data.get("price_points") or 0),
            "dividend_payments": int(data.get("dividend_payments") or 0),
        }

    def backfill_from_document_jsonb(
        self,
        *,
        symbols: Optional[Sequence[str]] = None,
        limit: int = 200,
        pending_only: bool = True,
    ) -> Dict[str, int]:
        """
        Copy ``price_history`` / ``dividend_history`` from JSONB into history tables.

        When ``symbols`` is omitted and ``pending_only`` is true (default), only symbols
        whose JSONB history is ahead of the normalized tables are processed.
        """
        if symbols:
            return self._sync_symbols(list(symbols))
        if pending_only:
            return self.sync_pending_from_jsonb(limit=limit)
        return self._sync_batch(limit=limit)

    def sync_pending_from_jsonb(self, *, limit: int = 500) -> Dict[str, int]:
        """Sync symbols where JSONB has more history rows than normalized tables."""
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        stats = {"processed": 0, "synced": 0, "skipped": 0, "pending": 0}

        with get_connection() as conn:
            rows = conn.execute(
                """
                WITH price_counts AS (
                  SELECT symbol, COUNT(*) AS n FROM stock_price_history GROUP BY symbol
                ),
                div_counts AS (
                  SELECT symbol, COUNT(*) AS n FROM stock_dividend_history GROUP BY symbol
                )
                SELECT
                  s.symbol,
                  s.document,
                  jsonb_array_length(COALESCE(s.document->'price_history', '[]'::jsonb)) AS json_prices,
                  jsonb_array_length(COALESCE(s.document->'dividend_history', '[]'::jsonb)) AS json_divs,
                  COALESCE(p.n, 0) AS table_prices,
                  COALESCE(d.n, 0) AS table_divs
                FROM stock_documents s
                LEFT JOIN price_counts p ON p.symbol = s.symbol
                LEFT JOIN div_counts d ON d.symbol = s.symbol
                WHERE jsonb_array_length(COALESCE(s.document->'price_history', '[]'::jsonb)) > COALESCE(p.n, 0)
                   OR jsonb_array_length(COALESCE(s.document->'dividend_history', '[]'::jsonb)) > COALESCE(d.n, 0)
                   OR (
                     COALESCE(p.n, 0) = 0
                     AND (
                       jsonb_array_length(COALESCE(s.document->'price_history', '[]'::jsonb)) > 0
                       OR NULLIF(s.document->>'price_history_json', '') IS NOT NULL
                     )
                   )
                   OR (
                     COALESCE(d.n, 0) = 0
                     AND (
                       jsonb_array_length(COALESCE(s.document->'dividend_history', '[]'::jsonb)) > 0
                       OR NULLIF(s.document->>'dividend_history_json', '') IS NOT NULL
                     )
                   )
                ORDER BY
                  (jsonb_array_length(COALESCE(s.document->'price_history', '[]'::jsonb)) - COALESCE(p.n, 0))
                  + (jsonb_array_length(COALESCE(s.document->'dividend_history', '[]'::jsonb)) - COALESCE(d.n, 0)) DESC,
                  s.symbol
                LIMIT %s
                """,
                (max(1, limit),),
            ).fetchall()

            stats["pending"] = len(rows)
            stats.update(self._sync_rows(rows, conn))

        logger.info(
            "History table sync (pending): pending=%s processed=%s synced=%s skipped=%s",
            stats["pending"],
            stats["processed"],
            stats["synced"],
            stats["skipped"],
        )
        return stats

    def _sync_batch(self, *, limit: int) -> Dict[str, int]:
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT symbol, document
                FROM stock_documents
                ORDER BY symbol
                LIMIT %s
                """,
                (max(1, limit),),
            ).fetchall()
            stats = {"processed": 0, "synced": 0, "skipped": 0, "pending": len(rows)}
            stats.update(self._sync_rows(rows, conn))
        return stats

    def _sync_symbols(self, symbols: Sequence[str]) -> Dict[str, int]:
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        targets = [symbol.upper() for symbol in symbols if symbol]
        stats = {"processed": 0, "synced": 0, "skipped": 0, "pending": len(targets)}
        if not targets:
            return stats

        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT symbol, document
                FROM stock_documents
                WHERE symbol = ANY(%s)
                ORDER BY symbol
                """,
                (targets,),
            ).fetchall()
            stats.update(self._sync_rows(rows, conn))
        return stats

    def _sync_rows(self, rows: Sequence[Any], conn: Any) -> Dict[str, int]:
        from data_ingestion.models import StockDocument
        from utils.stock_document_history import hydrate_document_history

        stats = {"processed": 0, "synced": 0, "skipped": 0}
        for row in rows:
            stats["processed"] += 1
            payload = row["document"]
            if not isinstance(payload, dict):
                payload = dict(payload)
            doc = StockDocument.from_dict(payload)
            doc.symbol = row["symbol"]
            doc = hydrate_document_history(doc)
            if not doc.price_history and not doc.dividend_history:
                stats["skipped"] += 1
                continue
            self.upsert_document_history(doc, conn=conn)
            stats["synced"] += 1
        return stats
