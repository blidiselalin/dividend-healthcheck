#!/usr/bin/env bash
# Copy local DividendScope data into ./data for Streamlit Community Cloud (git deploy).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SOURCE="${DIVIDENDSCOPE_DATA_DIR:-$HOME/.dividendscope/data}"
DEST="data"

if [[ ! -d "$SOURCE/vectordb" ]]; then
  echo "No vector DB at $SOURCE/vectordb"
  echo "Run locally first: python ingest_data.py --enrich && python ingest_data.py --sync-portfolio"
  exit 1
fi

echo "Source: $SOURCE"
echo "Dest:   $ROOT/$DEST"

rm -rf "$DEST/vectordb"
mkdir -p "$DEST"
cp -R "$SOURCE/vectordb" "$DEST/vectordb"

if [[ -f "$SOURCE/portfolio.db" ]]; then
  cp "$SOURCE/portfolio.db" "$DEST/portfolio.db"
  echo "Copied portfolio.db"
fi

SIZE="$(du -sh "$DEST/vectordb" | cut -f1)"
echo ""
echo "Done. vectordb size: $SIZE"
echo ""
echo "Next:"
echo "  git add data/vectordb data/portfolio.db 2>/dev/null || git add data/vectordb"
echo "  git commit -m 'Bundle data for Streamlit Cloud'"
echo "  git push"
echo ""
echo "Streamlit secrets (Settings → Secrets):"
echo '  DIVIDENDSCOPE_CLOUD = "true"'
echo '  DIVIDENDSCOPE_DATA_DIR = "data"'
