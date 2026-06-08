# DividendScope — Agent Guide

Read this before changing storage, portfolio logic, migrations, or tests.

## Production architecture

| Layer | Technology | Notes |
|-------|------------|--------|
| App | Streamlit (`app.py`) | HTTPS via host Caddy → `127.0.0.1:8501` |
| Database | **PostgreSQL 16** (Docker) | `DATABASE_URL` set in compose — **source of truth** |
| Market library | `stock_documents` (JSONB) | Shared S&P data; hourly refresh updates prices |
| Legacy import | `/data/users/`, `/data/vectordb/` | **Import only** via `migrate_to_cloud_sql.py` — not runtime |

**Do not** add runtime paths that write portfolio or market data to SQLite files or Chroma when `DATABASE_URL` is set.

## Data ownership

| Data | Tables / store | Scoped by |
|------|----------------|-----------|
| Users | `users`, `access_requests` | global |
| Holdings | `holdings` | `user_id` |
| Purchases | `purchase_journal` | `user_id` |
| Deposits | `monthly_deposits` | `user_id` |
| Net dividends (monthly) | `net_dividends` | `user_id` |
| Dividend receipts | `dividend_receipts` | `user_id` + symbol |
| Market docs | `stock_documents` | symbol (shared) |
| Price history | `stock_price_history` | symbol (shared) — yield charts |
| Dividend history | `stock_dividend_history` | symbol (shared) — yield charts, monthly exposure |

**Chroma legacy:** `price_history` / `dividend_history` (and `*_json` metadata) map to the two history tables above. `stock_documents.document` holds aggregated fundamentals; time series are normalized on PostgreSQL.

## Required patterns

### 1. Portfolio stores share one path

When code uses holdings + journal + dividends together, use:

```python
from services.portfolio_context import create_portfolio_context

ctx = create_portfolio_context()
ctx.portfolio.list_holdings()
ctx.journal.list_purchases()
```

Never construct `PortfolioStore()` and `PurchaseJournalStore()` separately in the same flow unless they share an explicit `db_path`.

### 2. Postgres date columns

PostgreSQL returns `date` / `datetime` objects, not strings. Always parse with:

```python
from db.parsing import parse_date, parse_optional_date
```

Never `date.fromisoformat(row["column"])` on DB rows.

### 3. Schema changes

- Add `migrations/00N_description.sql` (incrementing).
- `ensure_schema()` applies pending files tracked in `schema_migrations`.
- Mirror SQLite `CREATE TABLE` in store `_ensure_schema()` for local dev/tests only.
- Run `python -m db --migrate` on deploy (entrypoint does this).

### 4. Market library access

Runtime reads/writes go through:

- `services.shared_market_db.get_shared_vector_store()` / `get_document()`
- Enrichment: `data_ingestion.stock_enricher.create_stock_enricher()` (Yahoo + SEC EDGAR + Stooq, no API keys)

### 5. Holdings count

- **Runtime (Postgres):** `db.connection.holding_count_for_user()`
- **Explicit SQLite file (tests):** `utils.portfolio_db.sqlite_holding_count(path)` or `holding_count(path)` when path is a temp file
- `holding_count(db_path)` routes to Postgres when cloud SQL is active and path is the current user's portfolio file

### 6. Tests

- **Unit tests**: `PYTEST_USE_SQLITE=1` (autouse in `tests/conftest.py`) — no live Postgres.
- **Postgres mocks**: `@pytest.mark.postgres_mock` or `postgres_env` fixture (mock URL, not CI `:5432`).
- **Integration tests**: `@pytest.mark.integration` + live Postgres in CI (separate job).
- Pass explicit `tmp_path` / `db_path` into `create_portfolio_context(db_path=...)`.

## In-app assistant (chatbot)

- UI: `ui/chatbot_widget.py` — sidebar **Assistant** expander (`st.chat_message` + text form; no audio input).
- Logic: `services/chatbot_service.py` — curated FAQ first, optional Hugging Face **server-side** (`HUGGINGFACE_API_KEY` / `HF_TOKEN`).
- Do **not** call inference APIs from `components.html` / browser JS (CORS, token exposure).
- Disable UI: `DIVIDENDSCOPE_CHATBOT_ENABLED=0`.
- Tests: `tests/test_chatbot_service.py`.

## Safe change checklist

- [ ] Migrations added for Postgres schema changes?
- [ ] Store `_ensure_schema` updated for SQLite dev fallback?
- [ ] Date parsing uses `db.parsing`?
- [ ] Portfolio flows use `create_portfolio_context` or injected stores?
- [ ] Market reads use `shared_market_db`; enrichment uses `create_stock_enricher()`?
- [ ] Unit tests pass without `DATABASE_URL`?
- [ ] No new Chroma/SQLite runtime dependencies when `use_cloud_sql()`?
- [ ] Chatbot changes keep replies server-side and include educational disclaimer?

## Deploy (VM)

```bash
git pull && ./scripts/update_cloud_docker.sh
python -m db --migrate   # if entrypoint did not run
```

See `DEPLOY-GCP.md` for full ops.
