#!/usr/bin/env bash
# Legacy wrapper — price refresh now runs every 30 minutes.
# Kept so existing cron entries keep working until reinstalled.
exec "$(cd "$(dirname "$0")" && pwd)/price_refresh_30min.sh"
