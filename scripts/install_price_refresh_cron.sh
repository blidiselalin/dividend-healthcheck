#!/usr/bin/env bash
# Install cron job: refresh shared library prices every 30 minutes.
#
# Usage (on the VM, from repo root):
#   ./scripts/install_price_refresh_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$ROOT/scripts/price_refresh_30min.sh"
chmod +x "$ROOT/scripts/price_refresh_5min.sh" 2>/dev/null || true

CRON_CMD="cd $ROOT && ./scripts/price_refresh_30min.sh"
SCHEDULE="*/30 * * * *"
MARKER="# dividendscope-price-refresh-30min"
TMP="$(mktemp)"
# Replace any previous 5-minute or 30-minute price-refresh cron entries.
(crontab -l 2>/dev/null \
  | grep -v "dividendscope-price-refresh" \
  | grep -v "price_refresh_5min.sh" \
  | grep -v "price_refresh_30min.sh" \
  || true) >"$TMP"
echo "$SCHEDULE $CRON_CMD $MARKER" >>"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "Installed 30-minute price refresh cron:"
crontab -l | grep "$MARKER" || true
echo "Logs: $ROOT/logs/price-refresh.log"
echo "Note: the in-process scheduler (when DATABASE_URL is set) also refreshes every 30 minutes."
