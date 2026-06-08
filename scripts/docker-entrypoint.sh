#!/usr/bin/env bash
# Apply PostgreSQL schema on container start, then launch Streamlit.
set -euo pipefail
python -m db --migrate 2>/dev/null || true
python scripts/auto_import_market_library.py 2>/dev/null || true
exec "$@"
