#!/usr/bin/env bash
# Show PostgreSQL and legacy import paths on the Docker volume.
set -euo pipefail

VOLUME_NAME="${VOLUME_NAME:-dividendscope-persistent-data}"

echo "=== Docker volume: $VOLUME_NAME ==="
if ! docker volume inspect "$VOLUME_NAME" &>/dev/null; then
  echo "Volume not found. Start the stack first: docker compose up -d"
  exit 1
fi

docker volume inspect "$VOLUME_NAME" --format 'Mountpoint: {{ .Mountpoint }}'
echo ""

echo "=== /data layout ==="
docker run --rm -v "${VOLUME_NAME}:/data:ro" alpine:3.19 \
  sh -c '
    ls -la /data
    echo
    if [ -d /data/postgres ]; then
      du -sh /data/postgres
      echo "postgres: OK (primary storage)"
    else
      echo "postgres: not initialized — run docker compose up -d"
    fi
    if [ -d /data/vectordb ]; then
      du -sh /data/vectordb
      echo "vectordb: legacy import source only (runtime uses PostgreSQL stock_documents)"
    fi
    if [ -f /data/portfolio.db ] || [ -d /data/users ]; then
      echo "legacy SQLite: present (import with --migrate-files if not yet in Postgres)"
    fi
  '

echo ""
echo "=== PostgreSQL row counts (when stack is running) ==="
if docker compose ps dividendscope postgres 2>/dev/null | grep -q Up; then
  docker compose exec -T postgres psql -U "${POSTGRES_USER:-dividendscope}" -d "${POSTGRES_DB:-dividendscope}" -c "
    SELECT 'users' AS table_name, COUNT(*) FROM users
    UNION ALL SELECT 'holdings', COUNT(*) FROM holdings
    UNION ALL SELECT 'stock_documents', COUNT(*) FROM stock_documents;
  " 2>/dev/null || echo "(postgres query failed — check containers)"
else
  echo "Stack not running — start with: docker compose up -d"
fi
