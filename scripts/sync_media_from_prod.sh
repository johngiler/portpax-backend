#!/usr/bin/env bash
#
# Pull media objects from PRODUCTION S3 files bucket into local backend/media/.
# One-way only: S3 → local. Does not upload (push is manual via AWS CLI).
#
# Pull matrix (automated):
#   sync_db_from_dev.sh / sync_db_from_prod.sh
#   sync_media_from_dev.sh / sync_media_from_prod.sh (this script)
# Push to DEV/PROD: manual only — not scripted.
#
# Default bucket: itm-portpax-prod-files-040105284691 (override PORTPAX_FILES_BUCKET
# or --bucket=). Objects are synced as stored in the bucket (same relative paths
# as under MEDIA_ROOT). Use --prefix=media/ if keys live under that prefix.
#
# Requires: AWS CLI + profile/SSO with s3:ListBucket + s3:GetObject on the files bucket.
#   export AWS_PROFILE=portpax-prod
#
# Usage:
#   ./scripts/sync_media_from_prod.sh
#   ./scripts/sync_media_from_prod.sh --delete
#   ./scripts/sync_media_from_prod.sh --dry-run
#   ./scripts/sync_media_from_prod.sh --bucket=my-bucket --prefix=media/
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/_portpax_remote.sh
source "$SCRIPT_DIR/_portpax_remote.sh"

LOCAL_MEDIA="$BACKEND_DIR/media"
BUCKET="$PORTPAX_FILES_BUCKET"
PREFIX=""
DELETE=0
DRY_RUN=0

usage() {
  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
  case "$arg" in
    --delete) DELETE=1 ;;
    --dry-run|-n) DRY_RUN=1 ;;
    --bucket=*) BUCKET="${arg#--bucket=}" ;;
    --prefix=*) PREFIX="${arg#--prefix=}" ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      echo "Usage: $0 [--delete] [--dry-run] [--bucket=NAME] [--prefix=PATH/]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$BUCKET" ]]; then
  echo "ERROR: files bucket not set (PORTPAX_FILES_BUCKET / --bucket=)" >&2
  exit 1
fi

# Normalize prefix: no leading slash; trailing slash if non-empty
PREFIX="${PREFIX#/}"
if [[ -n "$PREFIX" && "$PREFIX" != */ ]]; then
  PREFIX="${PREFIX}/"
fi

S3_URI="s3://${BUCKET}/${PREFIX}"
mkdir -p "$LOCAL_MEDIA"

SYNC_EXTRA=()
if [[ "$DELETE" -eq 1 ]]; then
  SYNC_EXTRA+=(--delete)
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
  SYNC_EXTRA+=(--dryrun)
fi

echo "[sync_media_from_prod] ${S3_URI} → ${LOCAL_MEDIA}/"
portpax_s3_sync_down "$S3_URI" "$LOCAL_MEDIA/" "${SYNC_EXTRA[@]}"

echo "[sync_media_from_prod] Done."
