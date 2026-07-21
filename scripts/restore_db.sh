#!/usr/bin/env bash
#
# Replace the current Postgres database (from backend/.env) with a .sql dump.
# Drops the target database first, recreates it, then imports the file.
# Works on LOCAL / DEV / PRODUCTION (same .env contract).
#
# Usage:
#   ./scripts/restore_db.sh data/db/20260721-093015.sql
#   ./scripts/restore_db.sh 20260721-093015.sql          # looks under data/db/
#   ./scripts/restore_db.sh /path/to/dump.sql --yes      # skip confirm
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$BACKEND_DIR/.env"
DEFAULT_DUMP_DIR="$BACKEND_DIR/data/db"

YES=0
DUMP_ARG=""

for arg in "$@"; do
  case "$arg" in
    --yes|-y)
      YES=1
      ;;
    -h|--help)
      sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      if [[ -n "$DUMP_ARG" ]]; then
        echo "ERROR: unexpected argument: $arg" >&2
        exit 1
      fi
      DUMP_ARG="$arg"
      ;;
  esac
done

if [[ -z "$DUMP_ARG" ]]; then
  echo "Usage: $0 <dump.sql|--help> [--yes]" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
set -a
source "$ENV_FILE"
set +a

for v in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: $v not set in .env" >&2
    exit 1
  fi
done

HOST="${POSTGRES_HOST:-127.0.0.1}"
PORT="${POSTGRES_PORT:-5432}"

resolve_dump() {
  local path="$1"
  if [[ -f "$path" ]]; then
    printf '%s\n' "$(cd "$(dirname "$path")" && pwd)/$(basename "$path")"
    return
  fi
  if [[ -f "$DEFAULT_DUMP_DIR/$path" ]]; then
    printf '%s\n' "$DEFAULT_DUMP_DIR/$path"
    return
  fi
  if [[ -f "$BACKEND_DIR/$path" ]]; then
    printf '%s\n' "$(cd "$(dirname "$BACKEND_DIR/$path")" && pwd)/$(basename "$path")"
    return
  fi
  echo "ERROR: dump file not found: $path" >&2
  exit 1
}

DUMP_FILE="$(resolve_dump "$DUMP_ARG")"

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not found. Install PostgreSQL client tools." >&2
  exit 1
fi

echo "[restore_db] Target: $POSTGRES_DB @ ${HOST}:${PORT}"
echo "[restore_db] Source: $DUMP_FILE"
echo "[restore_db] This will DROP and recreate database «$POSTGRES_DB»."

if [[ "$YES" -ne 1 ]]; then
  read -r -p "Type YES to continue: " confirm
  if [[ "$confirm" != "YES" ]]; then
    echo "[restore_db] Aborted."
    exit 1
  fi
fi

export PGPASSWORD="$POSTGRES_PASSWORD"

PSQL=(psql --host="$HOST" --port="$PORT" --username="$POSTGRES_USER" --dbname=postgres -v ON_ERROR_STOP=1)

echo "[restore_db] Terminating open connections…"
"${PSQL[@]}" -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
  >/dev/null

echo "[restore_db] Dropping database…"
"${PSQL[@]}" -c "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\";"

echo "[restore_db] Creating database…"
"${PSQL[@]}" -c "CREATE DATABASE \"${POSTGRES_DB}\" OWNER \"${POSTGRES_USER}\";"

echo "[restore_db] Importing dump…"
# Make dumps more portable across Postgres majors:
# - strip PG17+ client SET transaction_timeout
# - strip pg_dump 17 \restrict / \unrestrict meta-commands
FILTERED="$(mktemp)"
trap 'rm -f "$FILTERED"' EXIT
grep -v -E \
  -e '^SET[[:space:]]+transaction_timeout[[:space:]]*=' \
  -e '^\\restrict([[:space:]]|$)' \
  -e '^\\unrestrict([[:space:]]|$)' \
  "$DUMP_FILE" >"$FILTERED"

psql \
  --host="$HOST" \
  --port="$PORT" \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  --file="$FILTERED"

echo "[restore_db] Done."
