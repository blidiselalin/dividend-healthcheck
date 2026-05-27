#!/usr/bin/env bash
# Pull latest code, rebuild the Docker image, and restart DividendScope on GCP/any host.
# Safe for persistent data: does NOT run `docker compose down -v`.
#
# Usage (on the VM):
#   cd ~/dividend-healthcheck
#   ./scripts/update_cloud_docker.sh
#
# Options:
#   --sync-portfolio   After restart, sync holdings → vector DB
#   --ingest           Populate shared S&P vectordb + enrich (slow; first-time or refresh)
#   --migrate-files    Import legacy SQLite/Chroma from /data into Postgres (one-time)
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

echo ">>> Rebuild image and restart containers (postgres + app volumes preserved)"
docker compose build --pull
# Remove stale manual container (docker run --name dividendscope) so compose can recreate
docker compose down --remove-orphans 2>/dev/null || true
docker rm -f dividendscope dividendscope-postgres 2>/dev/null || true
docker compose up -d

echo ">>> Apply PostgreSQL schema"
docker compose exec -T dividendscope python -m db.connection --migrate

echo ">>> Container status"
docker compose ps

if [[ "$MIGRATE_FILES" == true ]]; then
  echo ">>> Import legacy SQLite/Chroma from /data into PostgreSQL…"
  docker compose exec -T dividendscope python scripts/migrate_to_cloud_sql.py --data-dir /data
fi

if [[ "$RUN_INGEST" == true ]]; then
  echo ">>> Shared S&P library ingest (may take 30–90 min first time)…"
  docker compose exec -T dividendscope python ingest_data.py --ensure-sp500
  docker compose exec -T dividendscope python ingest_data.py --enrich-existing
fi

if [[ "$SYNC_PORTFOLIO" == true ]]; then
  echo ">>> Sync portfolio holdings → shared vector DB"
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
