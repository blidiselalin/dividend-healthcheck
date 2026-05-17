#!/usr/bin/env bash
# Show where DividendScope stores data in Docker and whether the volume has content.
set -euo pipefail

VOLUME_NAME="${VOLUME_NAME:-dividendscope-persistent-data}"

echo "=== Docker volume: $VOLUME_NAME ==="
if ! docker volume inspect "$VOLUME_NAME" &>/dev/null; then
  echo "Volume not found. Start the stack first: docker compose up -d"
  exit 1
fi

docker volume inspect "$VOLUME_NAME" --format 'Mountpoint: {{ .Mountpoint }}'
echo ""

echo "=== Contents (vectordb + portfolio.db) ==="
docker run --rm -v "${VOLUME_NAME}:/data:ro" alpine:3.19 \
  sh -c 'ls -la /data; echo; du -sh /data/vectordb 2>/dev/null || echo "vectordb: (empty — run ingest)"; ls -la /data/portfolio.db 2>/dev/null || true'
