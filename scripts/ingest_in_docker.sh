#!/usr/bin/env bash
# Run ingest_data.py inside Docker (persists to volume dividendscope-persistent-data → /data).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

EXTRA_ARGS=("$@")
CONTAINER="${CONTAINER_NAME:-dividendscope}"

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo ">>> docker exec -it $CONTAINER python ingest_data.py ${EXTRA_ARGS[*]}"
  docker exec -it "$CONTAINER" python ingest_data.py "${EXTRA_ARGS[@]}"
else
  echo ">>> Container '$CONTAINER' not running — using docker compose run (same /data volume)"
  docker compose run --rm dividendscope python ingest_data.py "${EXTRA_ARGS[@]}"
fi
