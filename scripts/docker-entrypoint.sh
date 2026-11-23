#!/usr/bin/env bash
# Apply PostgreSQL schema on container start, then launch Streamlit.
set -euo pipefail
CACHE_ROOT="${DIVIDENDSCOPE_DATA_DIR:-/data}/cache/yfinance"
mkdir -p "$CACHE_ROOT"
if [ -n "${DATABASE_URL:-}" ]; then
  migrated=0
  for _attempt in 1 2 3 4 5 6 7 8 9 10; do
    if python -m db --migrate; then
      migrated=1
      break
    fi
    echo "Waiting for Postgres before applying schema..."
    sleep 2
  done
  if [ "$migrated" -ne 1 ]; then
    echo "Postgres did not accept schema migrations."
    exit 1
  fi
fi
python scripts/auto_import_market_library.py 2>/dev/null || true
python -c "
from db.connection import use_cloud_sql
if use_cloud_sql():
    from db.postgres_market_history_store import PostgresMarketHistoryStore
    PostgresMarketHistoryStore().sync_pending_from_jsonb(limit=250)
" 2>/dev/null || true
exec "$@"
