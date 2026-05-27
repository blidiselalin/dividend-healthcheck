"""
PostgreSQL storage for the shared S&P market library (replaces ChromaDB).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PostgresMarketStore:
    """Persist StockDocument payloads as JSONB in Cloud SQL."""

    def add_document(self, document) -> str:
        return self.add_documents([document])[0]

    def add_documents(self, documents: List[Any]) -> List[str]:
        from data_ingestion.models import StockDocument
        from db.connection import ensure_schema, get_connection

        if not documents:
            return []

        ensure_schema()
        ids: List[str] = []
        with get_connection() as conn:
            for doc in documents:
                if not isinstance(doc, StockDocument):
                    continue
                payload = doc.to_full_dict()
                symbol = doc.symbol.upper()
                conn.execute(
                    """
                    INSERT INTO stock_documents (
                      symbol, document, sector, dividend_streak_years,
                      dividend_yield, data_quality, last_updated, source
                    ) VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      document = EXCLUDED.document,
                      sector = EXCLUDED.sector,
                      dividend_streak_years = EXCLUDED.dividend_streak_years,
                      dividend_yield = EXCLUDED.dividend_yield,
                      data_quality = EXCLUDED.data_quality,
                      last_updated = EXCLUDED.last_updated,
                      source = EXCLUDED.source
                    """,
                    (
                        symbol,
                        json.dumps(payload, default=_json_default),
                        doc.sector,
                        doc.dividend_streak_years,
                        doc.dividend_yield,
                        doc.data_quality,
                        doc.last_updated or datetime.now(),
                        doc.source.value if doc.source else "manual",
                    ),
                )
                ids.append(doc.document_id)
        return ids

    def get_by_symbol(self, symbol: str):
        from data_ingestion.models import StockDocument
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT document FROM stock_documents WHERE symbol = %s",
                (symbol.upper(),),
            ).fetchone()
        if not row:
            return None
        return StockDocument.from_dict(dict(row["document"]))

    def get_all_documents(self) -> List[Any]:
        from data_ingestion.models import StockDocument
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT document FROM stock_documents ORDER BY symbol"
            ).fetchall()
        return [StockDocument.from_dict(dict(row["document"])) for row in rows]

    def get_dividend_kings(self, min_streak: int = 50) -> List[Any]:
        from data_ingestion.models import StockDocument
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT document FROM stock_documents
                WHERE dividend_streak_years >= %s
                ORDER BY dividend_streak_years DESC
                """,
                (min_streak,),
            ).fetchall()
        return [StockDocument.from_dict(dict(row["document"])) for row in rows]

    def get_by_sector(self, sector: str) -> List[Any]:
        from data_ingestion.models import StockDocument
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT document FROM stock_documents
                WHERE lower(sector) = lower(%s)
                ORDER BY symbol
                """,
                (sector,),
            ).fetchall()
        return [StockDocument.from_dict(dict(row["document"])) for row in rows]

    def count(self) -> int:
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM stock_documents").fetchone()
        return int(row["count"]) if row else 0

    def delete_symbols(self, symbols: List[str]) -> int:
        from db.connection import ensure_schema, get_connection

        if not symbols:
            return 0
        ensure_schema()
        targets = [symbol.upper() for symbol in symbols]
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM stock_documents WHERE symbol = ANY(%s)",
                (targets,),
            )
        return cur.rowcount

    def clear(self) -> None:
        from db.connection import ensure_schema, get_connection

        ensure_schema()
        with get_connection() as conn:
            conn.execute("DELETE FROM stock_documents")

    def get_stats(self) -> Dict[str, Any]:
        docs = self.get_all_documents()
        stats: Dict[str, Any] = {
            "total_documents": len(docs),
            "dividend_kings": 0,
            "dividend_aristocrats": 0,
            "unique_symbols": len(docs),
            "sectors": {},
            "sources": {},
        }
        sectors: Dict[str, int] = {}
        sources: Dict[str, int] = {}
        for doc in docs:
            sector = doc.sector or "Unknown"
            sectors[sector] = sectors.get(sector, 0) + 1
            source = doc.source.value if doc.source else "unknown"
            sources[source] = sources.get(source, 0) + 1
            if doc.dividend_streak_years:
                if doc.dividend_streak_years >= 50:
                    stats["dividend_kings"] += 1
                elif doc.dividend_streak_years >= 25:
                    stats["dividend_aristocrats"] += 1
        stats["sectors"] = dict(sorted(sectors.items(), key=lambda item: item[1], reverse=True))
        stats["sources"] = dict(sorted(sources.items(), key=lambda item: item[1], reverse=True))
        return stats

    def search(self, query: str, n_results: int = 10, where: Optional[Dict[str, Any]] = None):
        from data_ingestion.vector_store import SearchResult

        query_lower = (query or "").lower()
        terms = [term for term in query_lower.split() if term]
        results: List[SearchResult] = []
        for doc in self.get_all_documents():
            if where and not _matches_filter(doc, where):
                continue
            text = doc.embedding_text.lower()
            score = sum(1 for term in terms if term in text) if terms else 0.1
            if score > 0:
                results.append(SearchResult(document=doc, score=score / max(len(terms), 1)))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:n_results]


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def _matches_filter(doc: Any, where: Dict[str, Any]) -> bool:
    for key, expected in where.items():
        actual = getattr(doc, key, None)
        if isinstance(expected, dict):
            if "$gte" in expected and (actual is None or actual < expected["$gte"]):
                return False
        elif actual != expected:
            return False
    return True
