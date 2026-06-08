#!/usr/bin/env bash
# Pull latest code, rebuild the Docker image, and restart DividendScope on GCP/any host.
# Safe for persistent data: does NOT run `docker compose down -v`.
#
# Usage (on the VM):
#   cd ~/dividend-healthcheck
#   ./scripts/update_cloud_docker.sh
#
# Options:
#   --sync-portfolio   After restart, sync holdings → PostgreSQL stock_documents
#   --ingest           Populate shared S&P library in PostgreSQL (slow; first-time or refresh)
#   --migrate-files    One-time import of legacy SQLite/Chroma files from /data into PostgreSQL
#   --no-pull          Skip git pull (used when code was rsync'd from local)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SYNC_PORTFOLIO=false
RUN_INGEST=false
MIGRATE_FILES=false
SKIP_PULL=false
for arg in "$@"; do
  case "$arg" in
    --sync-portfolio) SYNC_PORTFOLIO=true ;;
    --ingest) RUN_INGEST=true ;;
    --migrate-files) MIGRATE_FILES=true ;;
    --no-pull) SKIP_PULL=true ;;
    -h|--help)
      echo "Usage: $0 [--sync-portfolio] [--ingest] [--migrate-files] [--no-pull]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ "$SKIP_PULL" != true ]]; then
  echo ">>> Git pull"
  git pull --ff-only origin main || git pull --ff-only
else
  echo ">>> Skip git pull (deployed tree already on host)"
fi

echo ">>> Rebuild image and restart containers (volume dividendscope-persistent-data preserved)"
docker compose build --pull
# Remove stale manual container (docker run --name dividendscope) so compose can recreate
docker compose down --remove-orphans 2>/dev/null || true
docker rm -f dividendscope dividendscope-postgres 2>/dev/null || true
docker compose up -d

echo ">>> Apply PostgreSQL schema"
docker compose exec -T dividendscope python -m db --migrate

HOST_VDB="${ROOT}/data/vectordb"
if [[ -d "$HOST_VDB" ]] && [[ -n "$(ls -A "$HOST_VDB" 2>/dev/null)" ]]; then
  echo ">>> Copy project data/vectordb → persistent volume /data/vectordb"
  docker compose exec -T dividendscope mkdir -p /data/vectordb
  docker cp "$HOST_VDB/." dividendscope:/data/vectordb/
fi

echo ">>> Legacy market library (Chroma → PostgreSQL if /data/vectordb present)"
docker compose exec -T dividendscope python scripts/auto_import_market_library.py || true

if [[ "$MIGRATE_FILES" == true ]]; then
  echo ">>> Full legacy import (SQLite + Chroma → PostgreSQL)…"
  docker compose exec -T dividendscope python scripts/migrate_to_cloud_sql.py --data-dir /data --force-market
fi

echo ">>> Container status"
docker compose ps

if [[ "$RUN_INGEST" == true ]]; then
  echo ">>> Shared S&P library ingest (may take 30–90 min first time)…"
  docker compose exec -T dividendscope python ingest_data.py --ensure-sp500
  docker compose exec -T dividendscope python ingest_data.py --enrich-existing
  echo ">>> Backfill price/dividend history for yield channels (batched)…"
  docker compose exec -T dividendscope python ingest_data.py --backfill-history --backfill-limit 120
fi

if [[ "$SYNC_PORTFOLIO" == true ]]; then
  echo ">>> Sync portfolio holdings → PostgreSQL stock_documents"
  docker compose exec -T dividendscope python ingest_data.py --sync-portfolio
fi

PUBLIC_URL="${DIVIDENDSCOPE_PUBLIC_URL:-https://pulse-dividend.duckdns.org}"
VM_IP="$(curl -sf -H Metadata-Flavor:Google http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip 2>/dev/null || echo '')"
echo ""
echo "Done."
echo "  Public URL: ${PUBLIC_URL}"
echo "  Local only: http://127.0.0.1:8501 (Caddy proxies :443 → here)"
if [[ -n "$VM_IP" ]]; then
  echo "  Direct IP (if firewall 8501 open): http://${VM_IP}:8501"
fi
echo "Logs: docker compose logs -f dividendscope"
echo "Postgres: docker compose logs -f postgres"
