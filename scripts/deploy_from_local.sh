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
SSH_HOST="${SSH_HOST:-}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-dividend-healthcheck}"
DEPLOY_METHOD="${DEPLOY_METHOD:-rsync}"

SYNC_PORTFOLIO=false
RUN_INGEST=false
for arg in "$@"; do
  case "$arg" in
    --sync-portfolio) SYNC_PORTFOLIO=true ;;
    --ingest) RUN_INGEST=true ;;
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

REMOTE_APP_DIR="${REMOTE_APP_DIR#~/}"
REMOTE_APP_DIR="${REMOTE_APP_DIR#/}"

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
    gcloud compute ssh "$GCP_INSTANCE" \
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
    target="${SSH_HOST}:${REMOTE_APP_DIR}/"
  else
    target="${GCP_INSTANCE}:${REMOTE_APP_DIR}/"
  fi

  echo ">>> Rsync local project → ${target}"
  rsync -avz --delete \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude 'venv3.12/' \
    --exclude '__pycache__/' \
    --exclude '.git/' \
    --exclude '.cursor/' \
    --exclude 'data/downloads/' \
    --exclude 'data/vectordb/' \
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
  printf '%s' "$flags"
}

_rebuild_on_remote() {
  local flags
  flags=$(_build_remote_flags)

  echo ">>> Rebuild Docker on VM (volume /data preserved)"
  _remote_exec "cd ~/${REMOTE_APP_DIR} && chmod +x scripts/update_cloud_docker.sh scripts/run_tests.sh 2>/dev/null || true && ./scripts/update_cloud_docker.sh --no-pull${flags}"
}

_deploy_git() {
  echo ">>> Git pull on VM"
  _remote_exec "cd ~/${REMOTE_APP_DIR} && git fetch origin main && git reset --hard origin/main"
  _rebuild_on_remote
}

_main() {
  echo "Deploy method: $DEPLOY_METHOD"
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
