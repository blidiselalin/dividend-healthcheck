#!/usr/bin/env bash
# Apply PostgreSQL schema on container start, then launch Streamlit.
set -euo pipefail
python -m db --migrate 2>/dev/null || true
python scripts/auto_import_market_library.py 2>/dev/null || true
python -c "
from db.connection import use_cloud_sql
if use_cloud_sql():
    from db.postgres_market_history_store import PostgresMarketHistoryStore
    PostgresMarketHistoryStore().sync_pending_from_jsonb(limit=250)
" 2>/dev/null || true
exec "$@"
