#!/usr/bin/env bash
#
# Pull a Postgres dump from PRODUCTION (RDS via API EC2) and restore it.
#
# Pull matrix (automated):
#   sync_db_from_dev.sh / sync_db_from_prod.sh / sync_media_from_*
# Push to DEV/PROD: manual only (AWS CLI / SSH) — not scripted.
#
# Flow (no laptop→RDS):
#   1. SSM on PROD API → backup_db.sh (server .env → RDS)
#   2. EC2 uploads dump to s3://RELEASES/ops/db/<stamp>.sql
#   3. Laptop aws s3 cp → backend/data/db/
#   4. restore locally (default) or on DEV (--target=dev via SSH)
#
# Requires: AWS CLI + profile/SSO with SSM + S3 read on ops/db.
#   export AWS_PROFILE=portpax-prod   # or your SSO profile
# Instance role must allow s3:PutObject to ops/db/*.
#
# Usage:
#   ./scripts/sync_db_from_prod.sh
#   ./scripts/sync_db_from_prod.sh --yes
#   ./scripts/sync_db_from_prod.sh --target=dev --yes
#   ./scripts/sync_db_from_prod.sh --skip-backup   # reuse newest local ops dump name via --s3-key=
#   ./scripts/sync_db_from_prod.sh --s3-key=ops/db/20261117-120000.sql --yes
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/_portpax_remote.sh
source "$SCRIPT_DIR/_portpax_remote.sh"

LOCAL_DUMP_DIR="$BACKEND_DIR/data/db"
YES=0
TARGET="local"
SKIP_BACKUP=0
S3_KEY=""

usage() {
  sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --target=local) TARGET="local" ;;
    --target=dev) TARGET="dev" ;;
    --skip-backup) SKIP_BACKUP=1 ;;
    --s3-key=*) S3_KEY="${arg#--s3-key=}" ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      echo "Usage: $0 [--yes] [--target=local|dev] [--skip-backup] [--s3-key=ops/db/….sql]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$SCRIPT_DIR/restore_db.sh" ]]; then
  echo "ERROR: restore_db.sh not found at $SCRIPT_DIR/restore_db.sh" >&2
  exit 1
fi

mkdir -p "$LOCAL_DUMP_DIR"
BASENAME=""
S3_URI=""

if [[ -n "$S3_KEY" ]]; then
  # Reuse an existing object in the releases bucket.
  S3_URI="s3://${PORTPAX_RELEASES_BUCKET}/${S3_KEY#/}"
  BASENAME="$(basename "$S3_KEY")"
  echo "[sync_db_from_prod] Using existing ${S3_URI}"
elif [[ "$SKIP_BACKUP" -eq 1 ]]; then
  echo "ERROR: --skip-backup requires --s3-key=ops/db/<file>.sql" >&2
  exit 1
else
  echo "[sync_db_from_prod] 1/4 SSM backup on ${PORTPAX_PROD_INSTANCE_ID} → S3 ${PORTPAX_OPS_DB_PREFIX}/…"
  REMOTE_BODY=$(
    cat <<EOF
set -euo pipefail
cd '${PORTPAX_DEV_PATH}'
DUMP=\$(bash scripts/backup_db.sh | tee /dev/stderr | tail -n 1 | tr -d '\r')
if [ -z "\$DUMP" ] || [ "\${DUMP%.sql}" = "\$DUMP" ]; then
  echo "ERROR: could not parse dump path: \$DUMP" >&2
  exit 1
fi
BASE=\$(basename "\$DUMP")
DEST='s3://${PORTPAX_RELEASES_BUCKET}/${PORTPAX_OPS_DB_PREFIX}/'"\$BASE"
aws s3 cp "\$DUMP" "\$DEST" --region '${PORTPAX_AWS_REGION}'
echo "PORTPAX_DUMP_BASENAME=\$BASE"
EOF
  )

  SSM_OUT="$(portpax_ssm_run "PortPax sync_db_from_prod backup" "$REMOTE_BODY" | tee /dev/stderr)"
  BASENAME="$(
    printf '%s\n' "$SSM_OUT" \
      | tr -d '\r' \
      | grep -E '^PORTPAX_DUMP_BASENAME=' \
      | tail -n 1 \
      | cut -d= -f2-
  )"
  if [[ -z "$BASENAME" || "$BASENAME" != *.sql ]]; then
    echo "ERROR: could not parse PORTPAX_DUMP_BASENAME from SSM output." >&2
    echo "Got: ${BASENAME:-<empty>}" >&2
    exit 1
  fi
  S3_URI="s3://${PORTPAX_RELEASES_BUCKET}/${PORTPAX_OPS_DB_PREFIX}/${BASENAME}"
fi

LOCAL_DUMP="$LOCAL_DUMP_DIR/$BASENAME"

echo "[sync_db_from_prod] 2/4 Download ${S3_URI} → ${LOCAL_DUMP}"
portpax_s3_cp_down "$S3_URI" "$LOCAL_DUMP"

if [[ ! -s "$LOCAL_DUMP" ]]; then
  echo "ERROR: downloaded dump is missing or empty: $LOCAL_DUMP" >&2
  exit 1
fi

if [[ "$TARGET" == "local" ]]; then
  echo "[sync_db_from_prod] 3/4 Restore into LOCAL database..."
  RESTORE_ARGS=("$LOCAL_DUMP")
  if [[ "$YES" -eq 1 ]]; then
    RESTORE_ARGS+=(--yes)
  fi
  "$SCRIPT_DIR/restore_db.sh" "${RESTORE_ARGS[@]}"
  echo "[sync_db_from_prod] 4/4 Done. Local DB restored from $BASENAME"
  exit 0
fi

# --target=dev: scp dump + restore on DEV over SSH
portpax_require_ssh
REMOTE_DUMP="${PORTPAX_DEV_PATH}/data/db/${BASENAME}"

echo "[sync_db_from_prod] 3/4 Upload dump to ${PORTPAX_DEV_HOST}:${REMOTE_DUMP}"
ssh "$PORTPAX_DEV_HOST" "mkdir -p '${PORTPAX_DEV_PATH}/data/db'"
scp "$LOCAL_DUMP" "${PORTPAX_DEV_HOST}:${REMOTE_DUMP}"

echo "[sync_db_from_prod] 4/4 Restore on DEV (${PORTPAX_DEV_HOST})…"
RESTORE_REMOTE="./scripts/restore_db.sh 'data/db/${BASENAME}'"
if [[ "$YES" -eq 1 ]]; then
  RESTORE_REMOTE+=" --yes"
fi
ssh -t "$PORTPAX_DEV_HOST" "cd '${PORTPAX_DEV_PATH}' && ${RESTORE_REMOTE}"

echo "[sync_db_from_prod] Done. DEV DB restored from $BASENAME"
