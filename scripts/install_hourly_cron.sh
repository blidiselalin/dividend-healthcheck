#!/usr/bin/env bash
# Install a user crontab entry to refresh market data every hour.
#
# Usage (on the GCP VM, as the user that runs docker):
#   cd ~/dividend-healthcheck
#   ./scripts/install_hourly_cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
chmod +x "$ROOT/scripts/hourly_market_refresh.sh"

CRON_CMD="cd $ROOT && ./scripts/hourly_market_refresh.sh"
CRON_LINE="0 * * * * $CRON_CMD"

MARKER="# dividendscope-hourly-market"
TMP="$(mktemp)"
(crontab -l 2>/dev/null | grep -v "$MARKER" | grep -v "hourly_market_refresh.sh" || true) >"$TMP"
echo "$MARKER" >>"$TMP"
echo "$CRON_LINE" >>"$TMP"
crontab "$TMP"
rm -f "$TMP"

echo "Installed hourly cron:"
echo "  $CRON_LINE"
echo ""
echo "Logs: $ROOT/logs/hourly-market.log"
echo "Remove: crontab -e  (delete lines with $MARKER)"
