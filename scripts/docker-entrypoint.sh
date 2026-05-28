#!/usr/bin/env bash
# Bootstrap shared S&P market DB from image bundle when /data/vectordb is empty, then start Streamlit.
set -euo pipefail
python -c "
from services.shared_market_db import (
    bootstrap_shared_market_db_from_bundle,
    bootstrap_shared_market_db_to_postgres,
)
bootstrap_shared_market_db_from_bundle()
bootstrap_shared_market_db_to_postgres()
" 2>/dev/null || true
exec "$@"
