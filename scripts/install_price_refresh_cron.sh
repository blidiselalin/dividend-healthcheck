#!/usr/bin/env bash
# Install cron job: refresh shared library prices every 5 minutes.
#
# Usage (on the VM, from repo root):
#   ./scripts/install_price_refresh_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$ROOT/scripts/price_refresh_5min.sh"

CRON_CMD="cd $ROOT && ./scripts/price_refresh_5min.sh"
SCHEDULE="*/5 * * * *"
MARKER="# dividendscope-price-refresh-5min"
TMP="$(mktemp)"
(crontab -l 2>/dev/null | grep -v "$MARKER" | grep -v "price_refresh_5min.sh" || true) >"$TMP"
echo "$SCHEDULE $CRON_CMD $MARKER" >>"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "Installed 5-minute price refresh cron:"
crontab -l | grep "$MARKER" || true
echo "Logs: $ROOT/logs/price-refresh.log"
