# DividendScope — Agent Guide

Short index. Read the linked doc for the area you are changing.

## Quick rules

- **Production storage:** PostgreSQL when `DATABASE_URL` is set. No runtime Chroma/SQLite writes.
- **Scope:** Fix the task only — prefer 1–5 files. See `.cursor/rules/agent-discipline.mdc`.
- **Verify before done:** `pre-commit run --all-files` and `pytest -m "not integration"`.
- **Do not commit** unless the user asks.

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

- [ ] Migrations added for Postgres schema changes?
- [ ] Store `_ensure_schema` updated for SQLite dev fallback?
- [ ] Date parsing uses `db.parsing`?
- [ ] Portfolio flows use `create_portfolio_context` or injected stores?
- [ ] History dual-write via `PostgresMarketStore.add_documents()` or `PostgresMarketHistoryStore`?
- [ ] Unit tests pass without `DATABASE_URL`?
- [ ] No new Chroma/SQLite runtime dependencies when `use_cloud_sql()`?
- [ ] Portfolio UI uses `schedule_portfolio_reload()` / background jobs — not blocking rebuilds in render paths?
- [ ] IBKR import uses `portfolio_broker_import_service` + migration 009 (`source`/`side` columns)?
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
