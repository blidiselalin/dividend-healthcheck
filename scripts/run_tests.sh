#!/usr/bin/env bash
# Run the test suite locally (same commands as CI).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

if [[ -z "${DIVIDENDSCOPE_DATA_DIR:-}" ]]; then
  export DIVIDENDSCOPE_DATA_DIR="${TMPDIR:-/tmp}/dividendscope-test-data"
  mkdir -p "$DIVIDENDSCOPE_DATA_DIR"
fi

echo ">>> Running tests (DATA_DIR=$DIVIDENDSCOPE_DATA_DIR)"
"$PYTHON" -m pytest tests/ -v --tb=short "$@"
