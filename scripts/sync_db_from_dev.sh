#!/usr/bin/env bash
#
# Pull a fresh Postgres dump from DEV (portpax-api) into LOCAL and restore it.
#
# Pull matrix (automated):
#   sync_db_from_dev.sh      DEV → LOCAL (this script)
#   sync_db_from_prod.sh     PROD → LOCAL (or --target=dev)
#   sync_media_from_dev.sh / sync_media_from_prod.sh
# Push to DEV/PROD: manual only (AWS CLI / SSH) — not scripted.
#
# Steps:
#   1. ssh portpax-api → ./scripts/backup_db.sh
#   2. scp the dump → backend/data/db/
#   3. ./scripts/restore_db.sh <dump>  (local .env)
#
# Requires: SSH Host portpax-api (same as deploy.sh / sync_media_from_dev.sh).
#
# Usage (from backend/ or anywhere):
#   ./scripts/sync_db_from_dev.sh
#   ./scripts/sync_db_from_dev.sh --yes   # skip restore confirmation
#
# Compat: update_local_db.sh is a thin wrapper that calls this script.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/_portpax_remote.sh
source "$SCRIPT_DIR/_portpax_remote.sh"

REMOTE_HOST="$PORTPAX_DEV_HOST"
REMOTE_PATH="$PORTPAX_DEV_PATH"
LOCAL_DUMP_DIR="$BACKEND_DIR/data/db"

YES=0

for arg in "$@"; do
  case "$arg" in
    --yes|-y)
      YES=1
      ;;
    -h|--help)
      sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      echo "Usage: $0 [--yes]" >&2
      exit 1
      ;;
  esac
done

portpax_require_ssh

if [[ ! -f "$SCRIPT_DIR/restore_db.sh" ]]; then
  echo "ERROR: restore_db.sh not found at $SCRIPT_DIR/restore_db.sh" >&2
  exit 1
fi

mkdir -p "$LOCAL_DUMP_DIR"

echo "[sync_db_from_dev] 1/3 Backup on ${REMOTE_HOST}..."
REMOTE_DUMP="$(
  ssh "$REMOTE_HOST" "cd '$REMOTE_PATH' && bash scripts/backup_db.sh" \
    | tee /dev/stderr \
    | tail -n 1 \
    | tr -d '\r'
)"

if [[ -z "$REMOTE_DUMP" || "$REMOTE_DUMP" != *.sql ]]; then
  echo "ERROR: could not parse remote dump path from backup_db.sh output." >&2
  echo "Got: ${REMOTE_DUMP:-<empty>}" >&2
  exit 1
fi

BASENAME="$(basename "$REMOTE_DUMP")"
LOCAL_DUMP="$LOCAL_DUMP_DIR/$BASENAME"

echo "[sync_db_from_dev] 2/3 Download ${REMOTE_HOST}:${REMOTE_DUMP} → ${LOCAL_DUMP}"
scp "${REMOTE_HOST}:${REMOTE_DUMP}" "$LOCAL_DUMP"

if [[ ! -s "$LOCAL_DUMP" ]]; then
  echo "ERROR: downloaded dump is missing or empty: $LOCAL_DUMP" >&2
  exit 1
fi

echo "[sync_db_from_dev] 3/3 Restore into local database..."
RESTORE_ARGS=("$LOCAL_DUMP")
if [[ "$YES" -eq 1 ]]; then
  RESTORE_ARGS+=(--yes)
fi
"$SCRIPT_DIR/restore_db.sh" "${RESTORE_ARGS[@]}"

echo "[sync_db_from_dev] Done. Local DB restored from $BASENAME"
