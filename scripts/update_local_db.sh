#!/usr/bin/env bash
#
# Deprecated alias — use sync_db_from_dev.sh.
# Kept for existing habits / docs that still call update_local_db.sh.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[update_local_db] Deprecated: forwarding to sync_db_from_dev.sh" >&2
exec "$SCRIPT_DIR/sync_db_from_dev.sh" "$@"
