#!/usr/bin/env bash
# Manual run matching production settings (same as docker compose / Dockerfile).
# Prefer: docker compose up -d --build
#
# Prereqs: image built (docker compose build), Caddy on host → https://pulse-dividend.duckdns.org
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

IMAGE="${IMAGE:-dividend-healthcheck-dividendscope}"
NAME="${NAME:-dividendscope}"

docker rm -f "$NAME" 2>/dev/null || true

docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  -p 127.0.0.1:8501:8501 \
  -e DIVIDENDSCOPE_DATA_DIR=/data \
  -v dividendscope-persistent-data:/data \
  "$IMAGE" \
  streamlit run app.py \
  --server.port=8501 \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false

echo "Container $NAME started. Local: http://127.0.0.1:8501"
echo "Public (via Caddy): https://pulse-dividend.duckdns.org"
