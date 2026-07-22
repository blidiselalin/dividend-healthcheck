# DividendScope — Agent Guide

Short index. Read the linked doc for the area you are changing.

## Quick rules

- **Minimal diff:** fix the task only — prefer **1–5 files**. Search before adding; extend existing code; delete obsolete paths when replacing behavior. See `.cursor/rules/agent-discipline.mdc`.
- **Production storage:** PostgreSQL when `DATABASE_URL` is set. No runtime Chroma/SQLite writes.
- **Verify before done:** `pre-commit run --all-files` and `pytest -m "not integration"`.
- **Do not commit** unless the user asks.

## Obsolete — do not reintroduce

| Avoid | Use instead |
|-------|-------------|
| Legacy Excel broker parser / `portfolio_service.py` | `services/portfolio_broker_import_service.py` + `services/ibkr_activity_parser.py` |
| Runtime Chroma / per-user SQLite when `DATABASE_URL` set | `db.connection`, `create_portfolio_context()`, `shared_market_db` |
| `VectorStore(persist_directory=...)` in services/UI | `services.shared_market_db.get_document()` |
| `date.fromisoformat(row[...])` on DB rows | `db.parsing.parse_date` / `parse_optional_date` |
| Separate `PortfolioStore()` + `PurchaseJournalStore()` without shared path | `create_portfolio_context(db_path=...)` |
| `reload_portfolio_session()` in UI render paths | `schedule_portfolio_reload()`; IBKR apply → `reload_portfolio_after_data_import()` |
| `delete_holding()` when removing a sold IBKR position | `drop_holding()` — keeps journal + dividend receipts |
| `with st:` as context manager | `with st.sidebar:` or call `st.*` directly on main page |
| Broad refactors / “cleanup” across `ui/`, `services/`, `tests/` | Scoped fix in files the task touches |
| New helper file for one call site | Inline or extend the nearest existing module |

## Canonical modules (extend these)

| Area | Module |
|------|--------|
| Portfolio DB access | `services.portfolio_context.create_portfolio_context` |
| IBKR import | `services.portfolio_broker_import_service` |
| Portfolio reload (UI) | `services.portfolio_refresh.schedule_portfolio_reload` |
| Post-import sync reload | `services.portfolio_refresh.reload_portfolio_after_data_import` |
| Session / fingerprint | `services.portfolio_session` |
| Background work gate | `services.background_task_prefs` |
| Market library read | `services.shared_market_db` |
| Stock enrich | `data_ingestion.stock_enricher.create_stock_enricher` |
| Streamlit session keys | `ui/session_keys.py` (shared constants only) |
| Purchase journal views | `services.portfolio_purchase_journal_service` |
| Holding drill-down history | `services.portfolio_holding_detail_service` |

## Cursor rules (auto-loaded by area)

| Rule | When |
|------|------|
| `.cursor/rules/agent-discipline.mdc` | Always |
| `.cursor/rules/architecture.mdc` | Always |
| `.cursor/rules/ui-streamlit.mdc` | `ui/**`, `app.py` |
| `.cursor/rules/services-layer.mdc` | `services/**` |
| `.cursor/rules/postgres-data-layer.mdc` | `db/**`, `data_ingestion/**`, `migrations/**` |
| `.cursor/rules/tests.mdc` | `tests/**`, CI workflows |

## Deep dives

| Topic | Doc |
|-------|-----|
| Storage, migrations, stores | `.cursor/docs/agents/storage.md` |
| Portfolio UI session & chatbot | `.cursor/docs/agents/portfolio-ui.md` |
| Market library pipeline | `.cursor/docs/agents/market-library.md` |
| VM deploy | `DEPLOY-GCP.md` |

## Task playbooks

| Task | Doc |
|------|-----|
| Fix a failing test | `.cursor/docs/agent-tasks/fix-test.md` |
| Add a migration | `.cursor/docs/agent-tasks/add-migration.md` |
| Portfolio UI change | `.cursor/docs/agent-tasks/portfolio-ui-change.md` |

## Safe change checklist

- [ ] Smallest diff that fixes the task — no unrelated files?
- [ ] Existing module extended instead of a parallel copy?
- [ ] Obsolete code path removed or no longer called?
- [ ] Migrations added for Postgres schema changes?
- [ ] Store `_ensure_schema` updated for SQLite dev fallback?
- [ ] Date parsing uses `db.parsing`?
- [ ] Portfolio flows use `create_portfolio_context` or injected stores?
- [ ] History dual-write via `PostgresMarketStore.add_documents()` or `PostgresMarketHistoryStore`?
- [ ] Unit tests pass without `DATABASE_URL`?
- [ ] No new Chroma/SQLite runtime dependencies when `use_cloud_sql()`?
- [ ] Portfolio UI uses `schedule_portfolio_reload()` / background jobs — not blocking rebuilds in render paths?
- [ ] IBKR import uses `portfolio_broker_import_service` + migration 009 (`source`/`side` columns)?
- [ ] Sold positions use `drop_holding()` (merge import), not `delete_holding()`?
- [ ] Automatic background tasks respect `background_task_prefs.auto_background_tasks_enabled()` (off by default)?
- [ ] Chatbot replies stay server-side with educational disclaimer?

## Commands

```bash
# Lint & format
pre-commit run --all-files

# Unit tests (no live Postgres)
pytest -m "not integration" -q

# Integration tests (Postgres required)
pytest -m integration -q

# Apply pending migrations
python -m db --migrate

# Deploy (VM)
git pull && ./scripts/update_cloud_docker.sh
```
