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
#   --ingest           Run ingest_data.py --enrich (slow; first-time or refresh)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SYNC_PORTFOLIO=false
RUN_INGEST=false
for arg in "$@"; do
  case "$arg" in
    --sync-portfolio) SYNC_PORTFOLIO=true ;;
    --ingest) RUN_INGEST=true ;;
    -h|--help)
      echo "Usage: $0 [--sync-portfolio] [--ingest]"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

echo ">>> Git pull"
git pull --ff-only origin main || git pull --ff-only

echo ">>> Rebuild image and restart container (data volume preserved)"
docker compose build --pull
docker compose up -d

echo ">>> Container status"
docker compose ps

if [[ "$RUN_INGEST" == true ]]; then
  echo ">>> Ingest / enrich (may take 15–25 min)…"
  docker compose exec -T dividendscope python ingest_data.py --enrich
fi

if [[ "$SYNC_PORTFOLIO" == true ]] || [[ "$RUN_INGEST" == true ]]; then
  echo ">>> Sync portfolio → vector DB"
  docker compose exec -T dividendscope python ingest_data.py --sync-portfolio
fi

echo ""
echo "Done. App: http://$(curl -sf -H Metadata-Flavor:Google http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip 2>/dev/null || echo 'YOUR_VM_IP'):8501"
echo "Logs: docker compose logs -f dividendscope"
