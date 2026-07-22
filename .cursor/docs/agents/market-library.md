# Market library pipeline (agent deep dive)

One shared library, three layers. Legacy Chroma stored time series inside each document; Postgres splits them.

```
Legacy Chroma / fallback_store.json
        │  migrate_to_cloud_sql.py / auto_import_market_library.py
        ▼
stock_documents          ← aggregated fundamentals (JSONB + indexed columns)
        │  enrich / backfill / hourly update (yfinance)
        │  add_documents() dual-writes history arrays in JSONB
        ▼
stock_price_history      ← daily OHLCV (yield charts)
stock_dividend_history   ← ex-date payments (yield charts, monthly exposure)
```

## Commands

| Step | When | Command |
|------|------|---------|
| 1. Schema | Every deploy / container start | `python -m db --migrate` |
| 2. Legacy import | One-time if `/data/vectordb` exists | `./scripts/update_cloud_docker.sh --migrate-files` |
| 3. S&P populate | Empty library or refresh | `ingest_data.py --ensure-sp500 --enrich-existing` |
| 4. History enrich | Thin rows (<252 prices or <4 dividends) | `ingest_data.py --backfill-history --backfill-limit 120` |
| 5. JSONB → tables | Tables lag JSONB | `ingest_data.py --sync-history-tables` (repeat until synced=0) |

**Automatic on container start:** schema migrate → auto Chroma import → sync up to **250 pending** symbols.

**Admin UI:** Sidebar → **Sync history tables** (background job).

**Runtime reads:** `get_by_symbol()` merges `stock_documents` with history tables (prefers tables when richer).

**Post-import history sync** in `import_legacy_market_library()` is best-effort — failures must not abort the import.

## Agent discipline

- Read via `services.shared_market_db` — do not add new Chroma paths or local JSON runtime stores.
- Enrich via `create_stock_enricher()` — do not wire raw yfinance calls in UI or new one-off services.
- Backfill/sync scripts already exist (`ingest_data.py`, admin UI) — extend them instead of duplicate CLI tools.
