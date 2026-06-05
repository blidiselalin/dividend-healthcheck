"""
Read-only database inspection for admins — table validation and SELECT queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from db.connection import ensure_schema, get_connection, open_app_db, open_portfolio_db, use_cloud_sql

MANAGED_TABLES: Tuple[str, ...] = (
    "users",
    "access_requests",
    "holdings",
    "purchase_journal",
    "monthly_deposits",
    "net_dividends",
    "dividend_receipts",
    "stock_documents",
    "schema_migrations",
)

_SQLITE_PORTFOLIO_TABLES: Tuple[str, ...] = (
    "holdings",
    "purchase_journal",
    "monthly_deposits",
    "net_dividends",
    "dividend_receipts",
)

_SQLITE_APP_TABLES: Tuple[str, ...] = ("users", "access_requests", "schema_migrations")

_THIN_LIBRARY_WHERE = """
WHERE jsonb_array_length(COALESCE(document->'price_history', '[]'::jsonb)) < 252
   OR jsonb_array_length(COALESCE(document->'dividend_history', '[]'::jsonb)) < 4
""".strip()

_TABLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")

_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|"
    r"execute|call|merge|replace|attach|detach|pragma|vacuum)\b",
    re.IGNORECASE,
)

_DEFAULT_ROW_LIMIT = 500
_MAX_ROW_LIMIT = 2000
_QUERY_TIMEOUT_MS = 4000


@dataclass(frozen=True)
class TableCheck:
    name: str
    ok: bool
    row_count: int
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryResult:
    ok: bool
    columns: List[str]
    rows: List[Dict[str, Any]]
    message: str
    truncated: bool = False


def storage_label() -> str:
    return "PostgreSQL" if use_cloud_sql() else "SQLite (local dev)"


def is_safe_select_sql(sql: str) -> Tuple[bool, str]:
    """Return (allowed, reason). Only single-statement SELECT queries are permitted."""
    if not sql or not sql.strip():
        return False, "Query is empty."
    stripped = sql.strip()
    if ";" in stripped.rstrip(";"):
        return False, "Only one SQL statement is allowed."
    body = stripped.rstrip(";").strip()
    lower = body.lower()
    if not lower.startswith("select") and not lower.startswith("with"):
        return False, "Only SELECT queries (or WITH … SELECT) are allowed."
    if _FORBIDDEN_SQL.search(body):
        return False, "Query contains forbidden keywords."
    if "--" in body or "/*" in body:
        return False, "SQL comments are not allowed."
    return True, ""


def _apply_row_limit(sql: str, limit: int) -> Tuple[str, bool]:
    """Append LIMIT when missing; return (sql, was_truncated_by_us)."""
    body = sql.strip().rstrip(";")
    if re.search(r"\blimit\s+\d+", body, re.IGNORECASE):
        return body, False
    return f"{body} LIMIT {limit}", True


def _rows_to_dicts(columns: Sequence[str], rows: Sequence[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
            continue
        out.append({col: row[idx] for idx, col in enumerate(columns)})
    return out


def _safe_table_name(name: str, allowed: Sequence[str]) -> Optional[str]:
    if name not in allowed or not _TABLE_NAME.fullmatch(name):
        return None
    return name


def _fetch_scalar(conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    if isinstance(row, (int, float, str)):
        return row
    try:
        return row[0]
    except (TypeError, IndexError, KeyError):
        return row


def list_managed_tables() -> List[str]:
    if use_cloud_sql():
        ensure_schema()
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            ).fetchall()
        names = [r["table_name"] for r in rows]
        return [t for t in MANAGED_TABLES if t in names] + [
            t for t in names if t not in MANAGED_TABLES
        ]

    tables: List[str] = []
    with open_app_db() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        tables.extend(r["name"] if isinstance(r, dict) else r[0] for r in rows)
    with open_portfolio_db() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        for r in rows:
            name = r["name"] if isinstance(r, dict) else r[0]
            if name not in tables:
                tables.append(name)
    return tables


def table_row_counts(tables: Optional[Sequence[str]] = None) -> Dict[str, int]:
    names = list(tables) if tables is not None else list_managed_tables()
    counts: Dict[str, int] = {}
    if use_cloud_sql():
        ensure_schema()
        with get_connection() as conn:
            for table in names:
                safe = _safe_table_name(table, names)
                if not safe:
                    continue
                try:
                    counts[table] = int(_fetch_scalar(conn, f"SELECT COUNT(*) FROM {safe}"))
                except Exception:
                    counts[table] = -1
        return counts

    with open_app_db() as conn:
        for table in names:
            safe = _safe_table_name(table, names)
            if not safe:
                continue
            try:
                counts[table] = int(_fetch_scalar(conn, f"SELECT COUNT(*) FROM {safe}"))
            except Exception:
                pass
    with open_portfolio_db() as conn:
        for table in names:
            if table in counts:
                continue
            safe = _safe_table_name(table, names)
            if not safe:
                continue
            try:
                counts[table] = int(_fetch_scalar(conn, f"SELECT COUNT(*) FROM {safe}"))
            except Exception:
                pass
    return counts


def _validate_users(conn: Any) -> TableCheck:
    total = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM users"))
    active = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM users WHERE is_active = TRUE"))
    admins = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM users WHERE is_admin = TRUE"))
    ok = total >= 0
    return TableCheck(
        name="users",
        ok=ok,
        row_count=total,
        message=f"{active} active, {admins} admin",
        details={"active": active, "admins": admins},
    )


def _validate_access_requests(conn: Any) -> TableCheck:
    total = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM access_requests"))
    pending = int(
        _fetch_scalar(conn, "SELECT COUNT(*) FROM access_requests WHERE status = 'pending'")
    )
    return TableCheck(
        name="access_requests",
        ok=True,
        row_count=total,
        message=f"{pending} pending",
        details={"pending": pending},
    )


def _validate_holdings(conn: Any) -> TableCheck:
    total = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM holdings"))
    symbols = int(_fetch_scalar(conn, "SELECT COUNT(DISTINCT symbol) FROM holdings"))
    if use_cloud_sql():
        users = int(_fetch_scalar(conn, "SELECT COUNT(DISTINCT user_id) FROM holdings"))
        message = f"{users} users, {symbols} symbols"
        details: Dict[str, Any] = {"users": users, "symbols": symbols}
    else:
        message = f"{symbols} symbols"
        details = {"symbols": symbols}
    return TableCheck(
        name="holdings",
        ok=True,
        row_count=total,
        message=message,
        details=details,
    )


def _validate_simple_count(conn: Any, table: str) -> TableCheck:
    total = int(_fetch_scalar(conn, f"SELECT COUNT(*) FROM {table}"))
    return TableCheck(name=table, ok=True, row_count=total, message="Row count OK")


def _validate_stock_documents(conn: Any) -> TableCheck:
    if not use_cloud_sql():
        return TableCheck(
            name="stock_documents",
            ok=False,
            row_count=0,
            message="Library stats require PostgreSQL",
        )

    total = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM stock_documents"))
    if total == 0:
        return TableCheck(
            name="stock_documents",
            ok=False,
            row_count=0,
            message="No library documents — run ingest",
        )

    stats_sql = """
        SELECT
          COUNT(*) FILTER (
            WHERE jsonb_array_length(COALESCE(document->'price_history', '[]'::jsonb)) >= 252
          ) AS price_year_plus,
          COUNT(*) FILTER (
            WHERE jsonb_array_length(COALESCE(document->'dividend_history', '[]'::jsonb)) >= 4
          ) AS div_ttm_ready,
          COUNT(*) FILTER (
            WHERE jsonb_array_length(COALESCE(document->'price_history', '[]'::jsonb)) >= 500
          ) AS price_two_year_plus,
          MIN(last_updated) AS oldest_update,
          MAX(last_updated) AS newest_update
        FROM stock_documents
        """
    row = conn.execute(stats_sql).fetchone()
    details = dict(row) if isinstance(row, dict) else {}
    price_ok = int(details.get("price_year_plus") or 0)
    div_ok = int(details.get("div_ttm_ready") or 0)
    ok = price_ok > 0 and div_ok > 0
    msg = (
        f"{price_ok}/{total} with 1yr+ prices, "
        f"{div_ok}/{total} with 4+ dividend payments"
    )
    return TableCheck(
        name="stock_documents",
        ok=ok,
        row_count=total,
        message=msg,
        details=details,
    )


def _validate_schema_migrations(conn: Any) -> TableCheck:
    total = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM schema_migrations"))
    versions = conn.execute(
        "SELECT version, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    version_list = [
        v["version"] if isinstance(v, dict) else v[0] for v in versions
    ]
    ok = total > 0 and "001_initial" in version_list
    return TableCheck(
        name="schema_migrations",
        ok=ok,
        row_count=total,
        message=f"Applied: {', '.join(version_list) or 'none'}",
        details={"versions": version_list},
    )


_TABLE_VALIDATORS = {
    "users": _validate_users,
    "access_requests": _validate_access_requests,
    "holdings": _validate_holdings,
    "purchase_journal": lambda c: _validate_simple_count(c, "purchase_journal"),
    "monthly_deposits": lambda c: _validate_simple_count(c, "monthly_deposits"),
    "net_dividends": lambda c: _validate_simple_count(c, "net_dividends"),
    "dividend_receipts": lambda c: _validate_simple_count(c, "dividend_receipts"),
    "stock_documents": _validate_stock_documents,
    "schema_migrations": _validate_schema_migrations,
}


def _collect_table_checks(conn: Any, tables: Sequence[str]) -> List[TableCheck]:
    checks: List[TableCheck] = []
    for table in tables:
        validator = _TABLE_VALIDATORS.get(table)
        if validator is None:
            continue
        try:
            checks.append(validator(conn))
        except Exception as exc:
            checks.append(
                TableCheck(
                    name=table,
                    ok=False,
                    row_count=-1,
                    message=f"Validation failed: {exc}",
                )
            )
    return checks


def validate_all_tables() -> List[TableCheck]:
    checks: List[TableCheck] = []
    if use_cloud_sql():
        ensure_schema()
        with get_connection() as conn:
            checks.extend(_collect_table_checks(conn, MANAGED_TABLES))
        return checks

    with open_app_db() as conn:
        checks.extend(_collect_table_checks(conn, _SQLITE_APP_TABLES))
    with open_portfolio_db() as conn:
        checks.extend(_collect_table_checks(conn, _SQLITE_PORTFOLIO_TABLES))
    try:
        from services.shared_market_db import document_count

        count = document_count()
        checks.append(
            TableCheck(
                name="stock_documents (Chroma)",
                ok=count > 0,
                row_count=count,
                message="Local vector library — use PostgreSQL for SQL inspection",
                details={"storage": "chromadb"},
            )
        )
    except Exception as exc:
        checks.append(
            TableCheck(
                name="stock_documents (Chroma)",
                ok=False,
                row_count=0,
                message=str(exc),
            )
        )
    return checks


def inspect_stock_symbol(symbol: str) -> Dict[str, Any]:
    """Deep validation for one ticker in stock_documents (PostgreSQL)."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"ok": False, "message": "Symbol is required."}
    if not use_cloud_sql():
        try:
            from services.shared_market_db import get_shared_vector_store

            doc = get_shared_vector_store().get_by_symbol(sym)
            if doc is None:
                return {"ok": False, "symbol": sym, "message": "Not found in local library"}
            price_n = len(doc.price_history or [])
            div_n = len(doc.dividend_history or [])
            return {
                "ok": price_n >= 252 and div_n >= 4,
                "symbol": sym,
                "storage": "chromadb",
                "price_points": price_n,
                "dividend_payments": div_n,
                "sector": doc.sector,
                "last_updated": getattr(doc, "last_updated", None),
            }
        except Exception as exc:
            return {"ok": False, "symbol": sym, "message": str(exc)}

    ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
              symbol,
              sector,
              dividend_streak_years,
              dividend_yield,
              data_quality,
              last_updated,
              source,
              jsonb_array_length(COALESCE(document->'price_history', '[]'::jsonb)) AS price_points,
              jsonb_array_length(COALESCE(document->'dividend_history', '[]'::jsonb)) AS dividend_payments,
              document->'price_history'->0->>'date' AS first_price_date,
              document->'price_history'->-1->>'date' AS last_price_date,
              COALESCE(
                document->'dividend_history'->0->>'ex_date',
                document->'dividend_history'->0->>'date'
              ) AS first_dividend_date,
              COALESCE(
                document->'dividend_history'->-1->>'ex_date',
                document->'dividend_history'->-1->>'date'
              ) AS last_dividend_date
            FROM stock_documents
            WHERE symbol = %s
            """,
            (sym,),
        ).fetchone()
    if not row:
        return {"ok": False, "symbol": sym, "message": "Symbol not in stock_documents"}
    data = dict(row)
    price_pts = int(data.get("price_points") or 0)
    div_pts = int(data.get("dividend_payments") or 0)
    data["ok"] = price_pts >= 252 and div_pts >= 4
    data["yield_channel_ready"] = price_pts >= 120 and div_pts >= 4
    data["message"] = (
        f"{price_pts} price points, {div_pts} dividend payments"
        if data["ok"]
        else "Insufficient history for yield channel (need 252+ prices, 4+ dividends)"
    )
    return data


def sample_stock_documents_issues(*, limit: int = 25) -> List[Dict[str, Any]]:
    """Symbols with thin price or dividend history (PostgreSQL only)."""
    if not use_cloud_sql():
        return []
    ensure_schema()
    lim = max(1, min(limit, 100))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
              symbol,
              jsonb_array_length(COALESCE(document->'price_history', '[]'::jsonb)) AS price_points,
              jsonb_array_length(COALESCE(document->'dividend_history', '[]'::jsonb)) AS dividend_payments,
              last_updated
            FROM stock_documents
            {_THIN_LIBRARY_WHERE}
            ORDER BY price_points ASC, dividend_payments ASC
            LIMIT {lim}
            """
        ).fetchall()
    return [dict(r) for r in rows]


def sample_table_rows(
    table: str,
    *,
    allowed_tables: Sequence[str],
    limit: int = 50,
) -> QueryResult:
    safe = _safe_table_name(table, allowed_tables)
    if not safe:
        return QueryResult(
            ok=False,
            columns=[],
            rows=[],
            message="Invalid or disallowed table name.",
        )
    return run_readonly_query(f"SELECT * FROM {safe}", row_limit=limit)


def run_readonly_query(
    sql: str,
    *,
    row_limit: int = _DEFAULT_ROW_LIMIT,
) -> QueryResult:
    allowed, reason = is_safe_select_sql(sql)
    if not allowed:
        return QueryResult(ok=False, columns=[], rows=[], message=reason)

    limit = max(1, min(row_limit, _MAX_ROW_LIMIT))
    limited_sql, auto_limit = _apply_row_limit(sql, limit)

    try:
        if use_cloud_sql():
            ensure_schema()
            with get_connection() as conn:
                try:
                    timeout_ms = max(1, int(_QUERY_TIMEOUT_MS))
                except (TypeError, ValueError):
                    return QueryResult(
                        ok=False,
                        columns=[],
                        rows=[],
                        message="Invalid query timeout configuration.",
                    )
                # PostgreSQL SET LOCAL does not accept bind parameters for timeout values.
                conn.execute(
                    f"SET LOCAL statement_timeout = {timeout_ms}",
                )
                cur = conn.execute(limited_sql)
                rows = cur.fetchall()
                if rows and isinstance(rows[0], dict):
                    columns = list(rows[0].keys())
                elif getattr(cur, "description", None):
                    columns = [col.name for col in cur.description]
                else:
                    columns = []
        else:
            return _run_sqlite_select(limited_sql, auto_limit, limit)
    except Exception as exc:
        return QueryResult(ok=False, columns=[], rows=[], message=str(exc))

    dict_rows = _rows_to_dicts(columns, rows)
    for row in dict_rows:
        for key, val in list(row.items()):
            if isinstance(val, datetime):
                row[key] = val.astimezone(timezone.utc).isoformat()

    truncated = auto_limit and len(dict_rows) >= limit
    msg = f"{len(dict_rows)} row(s)"
    if truncated:
        msg += f" (limited to {limit})"
    return QueryResult(
        ok=True,
        columns=list(dict_rows[0].keys()) if dict_rows else columns,
        rows=dict_rows,
        message=msg,
        truncated=truncated,
    )


def _run_sqlite_select(sql: str, auto_limit: bool, row_limit: int) -> QueryResult:
    """Try app db first, then portfolio db for local SQLite."""
    last_error = ""
    for opener in (open_app_db, open_portfolio_db):
        try:
            with opener() as conn:
                cur = conn.execute(sql)
                rows = cur.fetchall()
                if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                    columns = list(rows[0].keys())
                elif rows:
                    columns = list(rows[0].keys()) if hasattr(rows[0], "keys") else []
                else:
                    columns = []
                dict_rows = _rows_to_dicts(columns, rows)
                msg = f"{len(dict_rows)} row(s)"
                if auto_limit:
                    msg += f" (limited to {row_limit})"
                return QueryResult(
                    ok=True,
                    columns=columns,
                    rows=dict_rows,
                    message=msg,
                    truncated=auto_limit and len(dict_rows) >= row_limit,
                )
        except Exception as exc:
            last_error = str(exc)
    return QueryResult(ok=False, columns=[], rows=[], message=last_error or "Query failed")


def preset_queries() -> Dict[str, str]:
    return {
        "All tables (row counts)": """
SELECT 'users' AS table_name, COUNT(*)::bigint AS rows FROM users
UNION ALL SELECT 'access_requests', COUNT(*)::bigint FROM access_requests
UNION ALL SELECT 'holdings', COUNT(*)::bigint FROM holdings
UNION ALL SELECT 'purchase_journal', COUNT(*)::bigint FROM purchase_journal
UNION ALL SELECT 'monthly_deposits', COUNT(*)::bigint FROM monthly_deposits
UNION ALL SELECT 'net_dividends', COUNT(*)::bigint FROM net_dividends
UNION ALL SELECT 'dividend_receipts', COUNT(*)::bigint FROM dividend_receipts
UNION ALL SELECT 'stock_documents', COUNT(*)::bigint FROM stock_documents
UNION ALL SELECT 'schema_migrations', COUNT(*)::bigint FROM schema_migrations
ORDER BY table_name
""".strip(),
        "Library coverage summary": """
SELECT
  COUNT(*) AS symbols,
  COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(document->'price_history', '[]'::jsonb)) >= 252) AS price_1yr_plus,
  COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(document->'dividend_history', '[]'::jsonb)) >= 4) AS div_4_plus,
  MIN(last_updated) AS oldest_update,
  MAX(last_updated) AS newest_update
FROM stock_documents
""".strip(),
        "Thin library symbols": f"""
SELECT
  symbol,
  jsonb_array_length(COALESCE(document->'price_history', '[]'::jsonb)) AS price_points,
  jsonb_array_length(COALESCE(document->'dividend_history', '[]'::jsonb)) AS dividend_payments,
  last_updated
FROM stock_documents
{_THIN_LIBRARY_WHERE}
ORDER BY price_points, dividend_payments
LIMIT 50
""".strip(),
        "Holdings by user": """
SELECT user_id, COUNT(*) AS holdings, SUM(shares) AS total_shares
FROM holdings
GROUP BY user_id
ORDER BY holdings DESC
""".strip(),
        "Recent dividend receipts": """
SELECT user_id, symbol, pay_date, gross_usd, recorded_at
FROM dividend_receipts
ORDER BY recorded_at DESC
LIMIT 50
""".strip(),
    }
