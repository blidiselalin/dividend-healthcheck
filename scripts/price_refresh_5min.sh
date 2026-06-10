#!/usr/bin/env bash
# Refresh live prices in the shared market library every 5 minutes (cron-friendly).
#
# Usage:
#   cd ~/dividend-healthcheck && ./scripts/price_refresh_5min.sh
#
# Cron (install via ./scripts/install_price_refresh_cron.sh):
#   */5 * * * * cd ~/dividend-healthcheck && ./scripts/price_refresh_5min.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG_DIR="${DIVIDENDSCOPE_LOG_DIR:-$ROOT/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/price-refresh.log"

LOCK_DIR="$LOG_DIR/.price-refresh.lock.d"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "$(date -Is) skip: previous price refresh still active" >>"$LOG_FILE"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

{
  echo ""
  echo "=== $(date -Is) price refresh ==="

  if ! docker compose ps --status running 2>/dev/null | grep -q dividendscope; then
    echo "Container not running; skipping."
    exit 0
  fi

  docker compose exec -T dividendscope python ingest_data.py --refresh-prices
  echo "=== done $(date -Is) ==="
} >>"$LOG_FILE" 2>&1
