# Storage & data layer (agent deep dive)

## Production architecture

| Layer | Technology | Notes |
|-------|------------|--------|
| App | Streamlit (`app.py`) | HTTPS via host Caddy → `127.0.0.1:8501` |
| Database | **PostgreSQL 16** (Docker) | `DATABASE_URL` — **source of truth** |
| Market library | `stock_documents` (JSONB) | Shared S&P data; hourly refresh |
| Legacy import | `/data/users/`, `/data/vectordb/` | **Import only** — not runtime |

**Do not** add runtime paths that write portfolio or market data to SQLite files or Chroma when `DATABASE_URL` is set.

## Data ownership

| Data | Tables / store | Scoped by |
|------|----------------|-----------|
| Users | `users`, `access_requests` | global |
| Holdings | `holdings` | `user_id` |
| Purchases | `purchase_journal` | `user_id` |
| Deposits | `monthly_deposits` | `user_id` |
| Net dividends | `net_dividends` | `user_id` |
| Dividend receipts | `dividend_receipts` | `user_id` + symbol |
| Market docs | `stock_documents` | symbol (shared) |
| Price history | `stock_price_history` | symbol (shared) |
| Dividend history | `stock_dividend_history` | symbol (shared) |

**Chroma legacy:** time series in JSONB map to `stock_price_history` and `stock_dividend_history`.

## Required patterns

### Portfolio stores share one path

```python
from services.portfolio_context import create_portfolio_context

ctx = create_portfolio_context()
ctx.portfolio.list_holdings()
ctx.journal.list_purchases()
```

Never construct `PortfolioStore()` and `PurchaseJournalStore()` separately unless they share an explicit `db_path`.

### Postgres date columns

```python
from db.parsing import parse_date, parse_optional_date
```

Never `date.fromisoformat(row["column"])` on DB rows.

### Schema changes

1. Add `migrations/00N_description.sql` (incrementing).
2. `ensure_schema()` applies pending files via `schema_migrations`.
3. Mirror SQLite `CREATE TABLE` in store `_ensure_schema()` for local dev/tests only.
4. Run `python -m db --migrate` on deploy.

### Market library access

- Read: `services.shared_market_db.get_document(symbol)`
- Enrich: `data_ingestion.stock_enricher.create_stock_enricher()`

### Holdings count

- **Runtime (Postgres):** `db.connection.holding_count_for_user()`
- **Tests (SQLite file):** `utils.portfolio_db.sqlite_holding_count(path)`
- `holding_count(db_path)` routes to Postgres when cloud SQL is active and path is the current user's file

### sqlite3.Row fingerprinting

When hashing DB rows, iterate **column names** — not the row itself:

```python
tuple(row[key] for key in row.keys())  # not: for key in row
```
