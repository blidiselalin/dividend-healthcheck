#!/usr/bin/env bash
# Deploy DividendScope from your laptop to the GCP VM (or any SSH host).
#
# 1. Copy deploy.env.example → deploy.env and set GCP_INSTANCE / ZONE / PROJECT or SSH_HOST
# 2. Run:
#      ./scripts/deploy_from_local.sh --sync-portfolio
#
# Methods:
#   rsync (default) — sync local project to VM, rebuild Docker (uses your working tree)
#   git             — SSH in and git pull + rebuild (VM must match GitHub)
#
# Options:
#   --sync-portfolio   Run ingest --sync-portfolio after restart
#   --ingest           Run ingest --enrich (slow)
#   --migrate-files    Import legacy SQLite + Chroma from /data into PostgreSQL
#   --include-vectordb   When rsyncing, include data/vectordb/ (large; needed for Chroma import)
#   --git              Force git pull on VM instead of rsync
#   --rsync            Force rsync (default)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/deploy.env" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/deploy.env"
fi

GCP_PROJECT="${GCP_PROJECT:-}"
GCP_INSTANCE="${GCP_INSTANCE:-}"
GCP_ZONE="${GCP_ZONE:-}"
GCP_SSH_USER="${GCP_SSH_USER:-}"
SSH_HOST="${SSH_HOST:-}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-dividend-healthcheck}"
REMOTE_APP_FULL_PATH="${REMOTE_APP_FULL_PATH:-}"
DEPLOY_METHOD="${DEPLOY_METHOD:-rsync}"

SYNC_PORTFOLIO=false
RUN_INGEST=false
MIGRATE_FILES=false
INCLUDE_VECTORDB=false
for arg in "$@"; do
  case "$arg" in
    --sync-portfolio) SYNC_PORTFOLIO=true ;;
    --ingest) RUN_INGEST=true ;;
    --migrate-files) MIGRATE_FILES=true ;;
    --include-vectordb) INCLUDE_VECTORDB=true ;;
    --git) DEPLOY_METHOD=git ;;
    --rsync) DEPLOY_METHOD=rsync ;;
    -h|--help)
      sed -n '1,20p' "$0"
      echo ""
      echo "Configure via deploy.env (see deploy.env.example)."
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

REMOTE_APP_CD=""

_resolve_remote_app_dir() {
  if [[ -n "$REMOTE_APP_FULL_PATH" ]]; then
    REMOTE_APP_CD="$REMOTE_APP_FULL_PATH"
    return
  fi

  local rel="${REMOTE_APP_DIR#~/}"
  rel="${rel#/}"
  local found
  found=$(_remote_exec "
    for d in \"\$HOME/${rel}\" \"\$HOME/dividend-healthcheck\" \"/home/blidiselalin/dividend-healthcheck\"; do
      if [[ -f \"\$d/docker-compose.yml\" ]]; then
        echo \"\$d\"
        exit 0
      fi
    done
    exit 1
  " 2>/dev/null || true)

  if [[ -z "$found" ]]; then
    echo "Could not find docker-compose.yml on the VM." >&2
    echo "Set REMOTE_APP_FULL_PATH in deploy.env (e.g. /home/blidiselalin/dividend-healthcheck)" >&2
    echo "Or GCP_SSH_USER=blidiselalin if the repo is under another Linux user." >&2
    echo "" >&2
    echo "Remote home listing:" >&2
    _remote_exec 'echo HOME=$HOME; ls -la $HOME; ls -la /home/*/dividend-healthcheck 2>/dev/null || true' || true
    exit 1
  fi
  REMOTE_APP_CD="$found"
  echo ">>> Using remote app dir: $REMOTE_APP_CD"
}

_gcloud_ssh_target() {
  if [[ -n "$GCP_SSH_USER" ]]; then
    echo "${GCP_SSH_USER}@${GCP_INSTANCE}"
  else
    echo "$GCP_INSTANCE"
  fi
}

_ssh_rsh() {
  if [[ -n "$SSH_HOST" ]]; then
    echo "ssh"
  elif command -v gcloud >/dev/null 2>&1; then
    echo "gcloud compute ssh --zone=${GCP_ZONE} --project=${GCP_PROJECT}"
  else
    echo ""
  fi
}

_remote_exec() {
  local cmd=$1
  if [[ -n "$SSH_HOST" ]]; then
    ssh -o BatchMode=yes "$SSH_HOST" "bash -lc $(printf '%q' "$cmd")"
  else
    if [[ -z "$GCP_INSTANCE" || -z "$GCP_ZONE" || -z "$GCP_PROJECT" ]]; then
      echo "Set GCP_INSTANCE, GCP_ZONE, GCP_PROJECT in deploy.env or set SSH_HOST." >&2
      exit 1
    fi
    gcloud compute ssh "$(_gcloud_ssh_target)" \
      --zone="$GCP_ZONE" \
      --project="$GCP_PROJECT" \
      --command="$cmd"
  fi
}

_rsync_to_remote() {
  local rsh
  rsh=$(_ssh_rsh)
  if [[ -z "$rsh" ]]; then
    echo "Install gcloud SDK or set SSH_HOST in deploy.env." >&2
    exit 1
  fi

  local target
  if [[ -n "$SSH_HOST" ]]; then
    target="${SSH_HOST}:${REMOTE_APP_CD:-${REMOTE_APP_DIR}}/"
  else
    target="$(_gcloud_ssh_target):${REMOTE_APP_CD:-${REMOTE_APP_DIR}}/"
  fi

  echo ">>> Rsync local project → ${target}"
  local exclude_vectordb=(--exclude 'data/vectordb/')
  if [[ "$INCLUDE_VECTORDB" == true ]]; then
    exclude_vectordb=()
    echo ">>> Including data/vectordb/ in rsync (legacy Chroma import source)"
  fi
  rsync -avz --delete \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude 'venv3.12/' \
    --exclude '__pycache__/' \
    --exclude '.git/' \
    --exclude '.cursor/' \
    --exclude 'data/downloads/' \
    "${exclude_vectordb[@]}" \
    --exclude 'data/portfolio.db' \
    --exclude 'data/*.db' \
    --exclude '.env' \
    --exclude 'deploy.env' \
    --exclude 'reports/' \
    --exclude '.DS_Store' \
    -e "$rsh" \
    "$ROOT/" "$target"
}

_build_remote_flags() {
  local flags=""
  [[ "$SYNC_PORTFOLIO" == true ]] && flags+=" --sync-portfolio"
  [[ "$RUN_INGEST" == true ]] && flags+=" --ingest"
  [[ "$MIGRATE_FILES" == true ]] && flags+=" --migrate-files"
  printf '%s' "$flags"
}

_rebuild_on_remote() {
  local flags
  flags=$(_build_remote_flags)

  echo ">>> Rebuild Docker on VM (volume /data preserved)"
  _remote_exec "cd $(printf '%q' "$REMOTE_APP_CD") && chmod +x scripts/update_cloud_docker.sh scripts/run_tests.sh 2>/dev/null || true && ./scripts/update_cloud_docker.sh --no-pull${flags}"
}

_deploy_git() {
  echo ">>> Git pull on VM"
  _remote_exec "cd $(printf '%q' "$REMOTE_APP_CD") && git fetch origin main && git reset --hard origin/main"
  _rebuild_on_remote
}

_main() {
  echo "Deploy method: $DEPLOY_METHOD"
  _resolve_remote_app_dir
  if [[ "$DEPLOY_METHOD" == "rsync" ]]; then
    _rsync_to_remote
    _rebuild_on_remote
  else
    _deploy_git
  fi
  echo ""
  echo "Deploy finished."
  if [[ -n "$SSH_HOST" ]]; then
    echo "Open: http://<your-vm-ip>:8501"
  else
    echo "Open: http://\$(gcloud compute instances describe ${GCP_INSTANCE} --zone=${GCP_ZONE} --project=${GCP_PROJECT} --format='get(networkInterfaces[0].accessConfigs[0].natIP)'):8501"
  fi
}

_main
