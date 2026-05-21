#!/usr/bin/env bash
# Copy local portfolio.db to ONE registered cloud user (safe when multiple users exist).
#
# Prerequisite: that person has signed in on the cloud app at least once (creates users.db row).
#
# Typical flow (multiple users on server):
#   1. Sign in on https://pulse-dividend.duckdns.org with YOUR Google account
#   2. ./scripts/migrate_portfolio_to_cloud.sh --list-users
#   3. ./scripts/migrate_portfolio_to_cloud.sh --email you@gmail.com --dry-run
#   4. ./scripts/migrate_portfolio_to_cloud.sh --email you@gmail.com --sync-portfolio --yes
#
# Only the matched user's /data/users/<id>/portfolio.db is written; everyone else is unchanged.
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
CONTAINER="${CONTAINER:-dividendscope}"
MIGRATE_EMAIL="${MIGRATE_EMAIL:-}"

LOCAL_DB=""
USER_ID=""
TARGET_EMAIL=""
LEGACY_ONLY=false
LIST_USERS=false
SYNC_PORTFOLIO=false
DRY_RUN=false
FORCE=false
ASSUME_YES=false

usage() {
  sed -n '1,16p' "$0"
  echo ""
  echo "Options:"
  echo "  --email ADDR     Target registered user (looks up id in cloud users.db)"
  echo "  --user-id ID     Target folder under /data/users/ (use id from --list-users)"
  echo "  --legacy-only    Write /data/portfolio.db only; does not touch /data/users/*"
  echo "  --local PATH     Local portfolio.db"
  echo "  --list-users     Registry + holdings (use before migrate on multi-user servers)"
  echo "  --sync-portfolio Run ingest --sync-portfolio after upload"
  echo "  --dry-run        Plan only"
  echo "  --force          Replace even if cloud user has more holdings"
  echo "  --yes            Skip confirmation"
  echo ""
  echo "deploy.env: MIGRATE_EMAIL=you@gmail.com (optional default for --email)"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local) shift; LOCAL_DB="${1:?--local requires path}"; shift ;;
    --user-id) shift; USER_ID="${1:?--user-id requires id}"; shift ;;
    --email) shift; TARGET_EMAIL="${1:?--email requires address}"; shift ;;
    --legacy-only) LEGACY_ONLY=true ;;
    --list-users) LIST_USERS=true ;;
    --sync-portfolio) SYNC_PORTFOLIO=true ;;
    --dry-run) DRY_RUN=true ;;
    --force) FORCE=true ;;
    --yes) ASSUME_YES=true ;;
    -h|--help) usage; exit 0 ;;
    --local=*) LOCAL_DB="${1#*=}"; shift ;;
    --user-id=*) USER_ID="${1#*=}"; shift ;;
    --email=*) TARGET_EMAIL="${1#*=}"; shift ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$TARGET_EMAIL" && -n "$MIGRATE_EMAIL" ]]; then
  TARGET_EMAIL="$MIGRATE_EMAIL"
fi

_gcloud_ssh_target() {
  if [[ -n "$GCP_SSH_USER" ]]; then
    echo "${GCP_SSH_USER}@${GCP_INSTANCE}"
  else
    echo "$GCP_INSTANCE"
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

_resolve_local_db() {
  if [[ -n "$LOCAL_DB" ]]; then
    echo "$LOCAL_DB"
    return
  fi
  for path in "$HOME/.dividendscope/data/portfolio.db" "$ROOT/data/portfolio.db"; do
    if [[ -f "$path" ]]; then
      echo "$path"
      return
    fi
  done
  local user_dbs=()
  while IFS= read -r -d '' f; do
    user_dbs+=("$f")
  done < <(find "$HOME/.dividendscope/data/users" "$ROOT/data/users" -name portfolio.db -print0 2>/dev/null || true)
  if [[ ${#user_dbs[@]} -eq 1 ]]; then
    echo "${user_dbs[0]}"
    return
  fi
  if [[ ${#user_dbs[@]} -gt 1 ]]; then
    echo "Multiple local user databases. Use --local:" >&2
    printf '  %s\n' "${user_dbs[@]}" >&2
    exit 1
  fi
  echo ""
}

_holding_count() {
  local db=$1
  if [[ ! -f "$db" ]]; then
    echo 0
    return
  fi
  sqlite3 "$db" "SELECT COUNT(*) FROM holdings;" 2>/dev/null || echo 0
}

_resolve_remote_app_dir() {
  if [[ -n "$REMOTE_APP_FULL_PATH" ]]; then
    echo "$REMOTE_APP_FULL_PATH"
    return
  fi
  local rel="${REMOTE_APP_DIR#~/}"
  rel="${rel#/}"
  _remote_exec "
    for d in \"\$HOME/${rel}\" \"\$HOME/dividend-healthcheck\"; do
      if [[ -f \"\$d/docker-compose.yml\" ]]; then
        echo \"\$d\"
        exit 0
      fi
    done
    exit 1
  " 2>/dev/null
}

_remote_list_users_script() {
  cat <<'REMOTE_LIST'
docker exec __CONTAINER__ sh -c '
holdings() {
  db="$1"
  if [ -f "$db" ]; then
    sqlite3 "$db" "SELECT COUNT(*) FROM holdings;" 2>/dev/null || echo 0
  else
    echo 0
  fi
}
echo "=== Registered users (users.db) — use --email to target one ==="
if [ -f /data/users.db ]; then
  sqlite3 -separator "|" /data/users.db "
    SELECT id, lower(email), is_active, is_admin
    FROM users ORDER BY last_login_at DESC;
  " 2>/dev/null | while IFS="|" read -r uid email active admin; do
    [ -n "$uid" ] || continue
    db="/data/users/${uid}/portfolio.db"
    n=$(holdings "$db")
    folder=no
    [ -d "/data/users/${uid}" ] && folder=yes
    echo "REG|${uid}|${email}|holdings=${n}|folder=${folder}|active=${active}|admin=${admin}"
  done
else
  echo "REG|(users.db missing — no one has signed in yet)"
fi
echo ""
echo "=== Folders without registry (orphan — not matched by --email) ==="
if [ -d /data/users ]; then
  for d in /data/users/*/; do
    [ -d "$d" ] || continue
    uid=$(basename "$d")
    if [ -f /data/users.db ]; then
      hit=$(sqlite3 /data/users.db "SELECT 1 FROM users WHERE id='$uid' LIMIT 1;" 2>/dev/null || true)
      [ -n "$hit" ] && continue
    fi
    n=$(holdings "$d/portfolio.db")
    echo "ORPHAN|${uid}|holdings=${n}"
  done
fi
echo ""
echo "=== Legacy shared file (admin migration only; does not change other users) ==="
if [ -f /data/portfolio.db ]; then
  n=$(holdings /data/portfolio.db)
  echo "LEGACY|/data/portfolio.db|holdings=${n}"
else
  echo "LEGACY|/data/portfolio.db|missing"
fi
'
REMOTE_LIST
}

_print_list_users() {
  local script
  script=$(_remote_list_users_script)
  script="${script//__CONTAINER__/${CONTAINER}}"
  local out
  out=$(_remote_exec "$script" 2>/dev/null) || {
    echo "(Could not list — is container ${CONTAINER} running?)" >&2
    return 1
  }
  printf '%s\n' "$out" | while IFS= read -r line; do
    case "$line" in
      ===*) echo "$line" ;;
      REG\|*) 
        IFS='|' read -r _ uid email rest <<< "$line"
        printf '  %-28s %-32s %s\n' "$uid" "$email" "$rest"
        ;;
      ORPHAN\|*)
        IFS='|' read -r _ uid rest <<< "$line"
        printf '  %-28s %s (not in users.db)\n' "$uid" "$rest"
        ;;
      LEGACY\|*)
        IFS='|' read -r _ path rest <<< "$line"
        printf '  %s %s\n' "$path" "$rest"
        ;;
      *) echo "$line" ;;
    esac
  done
  echo ""
  echo "Migrate ONE registered user: $0 --email you@gmail.com --dry-run"
}

_resolve_user_id_from_email() {
  local email_lower
  email_lower=$(echo "$1" | tr '[:upper:]' '[:lower:]' | xargs)
  local script
  script="docker exec $(printf '%q' "$CONTAINER") sqlite3 /data/users.db \
    \"SELECT id FROM users WHERE lower(email) = '$(printf '%s' "$email_lower" | sed "s/'/''/g")' LIMIT 2;\" 2>/dev/null"
  local ids
  ids=$(_remote_exec "$script" 2>/dev/null || true)
  ids=$(echo "$ids" | sed '/^$/d')
  local count
  count=$(echo "$ids" | wc -l | tr -d ' ')
  if [[ "$count" == "0" || -z "$ids" ]]; then
    echo ""
    return 1
  fi
  if [[ "$count" -gt 1 ]]; then
    echo "MULTIPLE"
    return 2
  fi
  echo "$ids" | head -1
}

if [[ "$LIST_USERS" == true ]]; then
  _print_list_users
  exit 0
fi

REMOTE_APP="$(_resolve_remote_app_dir)" || {
  echo "Remote app dir not found. Set REMOTE_APP_FULL_PATH in deploy.env." >&2
  exit 1
}

if [[ "$LEGACY_ONLY" != true && -z "$USER_ID" && -z "$TARGET_EMAIL" ]]; then
  echo "Specify exactly one target (other users will not be modified):" >&2
  echo "  $0 --list-users" >&2
  echo "  $0 --email you@gmail.com     # registered Google account (recommended)" >&2
  echo "  $0 --user-id <folder-id>     # from REG line in --list-users" >&2
  exit 1
fi

if [[ -n "$TARGET_EMAIL" && -n "$USER_ID" ]]; then
  echo "Use only one of --email or --user-id." >&2
  exit 1
fi

if [[ -n "$TARGET_EMAIL" ]]; then
  echo ">>> Resolving cloud user id for: $TARGET_EMAIL"
  resolved=$(_resolve_user_id_from_email "$TARGET_EMAIL") || resolve_code=$?
  resolve_code=${resolve_code:-0}
  if [[ "${resolved:-}" == "MULTIPLE" ]]; then
    echo "Multiple users share this email in users.db — contact admin." >&2
    exit 1
  fi
  if [[ -z "${resolved:-}" ]]; then
    echo "No registered user with email $TARGET_EMAIL on the cloud server." >&2
    echo "" >&2
    echo "That account must sign in once before migration:" >&2
    echo "  https://pulse-dividend.duckdns.org" >&2
    echo "Then run: $0 --list-users" >&2
    exit 1
  fi
  USER_ID="$resolved"
  echo ">>> Matched registered user id: $USER_ID"
fi

if [[ -n "$USER_ID" ]] && [[ ! "$USER_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Invalid --user-id." >&2
  exit 1
fi

LOCAL_DB="$(_resolve_local_db)"
if [[ ! -f "$LOCAL_DB" ]]; then
  echo "Local portfolio.db not found. Use --local PATH" >&2
  exit 1
fi

LOCAL_HOLDINGS="$(_holding_count "$LOCAL_DB")"

if [[ "$LEGACY_ONLY" == true ]]; then
  TARGET_PATH="/data/portfolio.db"
  TARGET_LABEL="legacy /data/portfolio.db (users under /data/users/ unchanged)"
else
  TARGET_PATH="/data/users/${USER_ID}/portfolio.db"
  if [[ -n "$TARGET_EMAIL" ]]; then
    TARGET_LABEL="registered user ${TARGET_EMAIL} → ${TARGET_PATH}"
  else
    TARGET_LABEL="${TARGET_PATH}"
  fi
fi

echo ">>> Local: $LOCAL_DB ($LOCAL_HOLDINGS holdings)"
echo ">>> Target (only this file): $TARGET_LABEL"
echo ">>> All other /data/users/* portfolios: unchanged"

REMOTE_CHECK="
set -e
cd $(printf '%q' "$REMOTE_APP")
docker ps --format '{{.Names}}' | grep -qx $(printf '%q' "$CONTAINER")
TARGET=$(printf '%q' "$TARGET_PATH")
LOCAL_H=$LOCAL_HOLDINGS
FORCE=$([[ "$FORCE" == true ]] && echo true || echo false)
count=0
if docker exec $(printf '%q' "$CONTAINER") test -f \"\$TARGET\"; then
  count=\$(docker exec $(printf '%q' "$CONTAINER") sqlite3 \"\$TARGET\" 'SELECT COUNT(*) FROM holdings;' 2>/dev/null || echo 0)
fi
echo \"Remote holdings at target: \$count\"
if [ \"\$FORCE\" != true ] && [ \"\$count\" -gt \"\$LOCAL_H\" ]; then
  echo 'Abort: remote has more holdings than local. Use --force to replace.' >&2
  exit 2
fi
nusers=\$(docker exec $(printf '%q' "$CONTAINER") sh -c 'ls -1 /data/users 2>/dev/null | wc -l' || echo 0)
echo \"Other user folders on server: \$(( nusers > 0 ? nusers - 1 : 0 )) (not modified)\"
"

set +e
_remote_exec "$REMOTE_CHECK"
check_code=$?
set -e
if [[ "$check_code" == 2 ]]; then
  exit 1
fi
if [[ "$check_code" != 0 ]]; then
  echo "Remote check failed." >&2
  exit 1
fi

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run complete — no files written."
  exit 0
fi

if [[ "$ASSUME_YES" != true ]]; then
  read -r -p "Overwrite ONLY this target? Other users unchanged. [y/N] " confirm
  confirm=$(echo "$confirm" | tr '[:upper:]' '[:lower:]')
  if [[ "$confirm" != "y" && "$confirm" != "yes" ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

TMP_REMOTE="/tmp/dividendscope-portfolio-migrate-$$.db"
if [[ -n "$SSH_HOST" ]]; then
  scp -o BatchMode=yes "$LOCAL_DB" "${SSH_HOST}:${TMP_REMOTE}"
else
  gcloud compute scp "$LOCAL_DB" "$(_gcloud_ssh_target):${TMP_REMOTE}" \
    --zone="$GCP_ZONE" --project="$GCP_PROJECT"
fi

_remote_exec "
set -e
cd $(printf '%q' "$REMOTE_APP")
TS=\$(date +%Y%m%d%H%M%S)
TARGET=$(printf '%q' "$TARGET_PATH")
TMP=$(printf '%q' "$TMP_REMOTE")
docker exec $(printf '%q' "$CONTAINER") mkdir -p \"\$(dirname \"\$TARGET\")\"
docker exec $(printf '%q' "$CONTAINER") sh -c \"[ -f \\\"\$TARGET\\\" ] && cp \\\"\$TARGET\\\" \\\"\${TARGET}.bak.\${TS}\\\" || true\"
docker cp \"\$TMP\" $(printf '%q' "$CONTAINER"):\$TARGET
rm -f \"\$TMP\"
echo \"Wrote \$TARGET (backup: \${TARGET}.bak.\${TS} if existed)\"
docker compose restart $(printf '%q' "$CONTAINER") 2>/dev/null || docker restart $(printf '%q' "$CONTAINER")
"

if [[ "$SYNC_PORTFOLIO" == true ]]; then
  echo ">>> Syncing holdings to vector DB (shared library; does not change other users SQLite)..."
  _remote_exec "cd $(printf '%q' "$REMOTE_APP") && docker compose exec -T $(printf '%q' "$CONTAINER") python ingest_data.py --sync-portfolio"
fi

echo ""
echo "Done."
echo "  Sign in as ${TARGET_EMAIL:-$USER_ID} on https://pulse-dividend.duckdns.org"
echo "  Other registered users' portfolios were not modified."
