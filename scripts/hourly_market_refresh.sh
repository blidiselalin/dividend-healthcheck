#!/usr/bin/env bash
# Hourly market refresh for production (prices + batched enrich + S&P catch-up).
#
# Usage on the VM:
#   cd ~/dividend-healthcheck && ./scripts/hourly_market_refresh.sh
#
# Cron (install via ./scripts/install_hourly_cron.sh):
#   0 * * * * cd ~/dividend-healthcheck && ./scripts/hourly_market_refresh.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG_DIR="${DIVIDENDSCOPE_LOG_DIR:-$ROOT/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/hourly-market.log"

LOCK_DIR="$LOG_DIR/.hourly-market.lock.d"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "$(date -Is) skip: previous hourly run still active" >>"$LOG_FILE"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

{
  echo ""
  echo "=== $(date -Is) hourly market refresh ==="

  if ! docker compose ps --status running 2>/dev/null | grep -q dividendscope; then
    echo "Container not running; skipping."
    exit 0
  fi

  docker compose exec -T dividendscope python ingest_data.py --hourly-update
  echo "=== done $(date -Is) ==="
} >>"$LOG_FILE" 2>&1
