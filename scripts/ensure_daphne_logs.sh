#!/usr/bin/env bash
# Compat wrapper — prefer ensure_app_logs.sh (creates all API unit logs).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/ensure_app_logs.sh"
