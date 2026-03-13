#!/usr/bin/env bash
#
# Deploy PortPax backend to api.portpax.com (portpax-api).
# Requires: rsync, SSH config Host portpax-api -> api.portpax.com, root.
# Target: /home/git/backend (server runs gunicorn via systemd).
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REMOTE_HOST="portpax-api"
REMOTE_PATH="/home/git/backend"

# Exclude venv, db, cache, secrets, prod-only files (exist only on server)
RSYNC_EXCLUDE=(
  --exclude ".venv"
  --exclude "__pycache__"
  --exclude "*.pyc"
  --exclude ".env"
  --exclude "config/local_settings.py"
  --exclude "db.sqlite3"
  --exclude "staticfiles"
  --exclude ".git"
)

cd "$BACKEND_DIR"

echo "[deploy] Syncing backend -> $REMOTE_HOST:$REMOTE_PATH"
rsync -avz --delete "${RSYNC_EXCLUDE[@]}" -e ssh "$BACKEND_DIR/" "$REMOTE_HOST:$REMOTE_PATH/"

echo "[deploy] Fixing ownership and running: install deps, migrate, collectstatic, restart..."
ssh "$REMOTE_HOST" "chown -R git:git $REMOTE_PATH"
ssh "$REMOTE_HOST" "cd $REMOTE_PATH && sudo -u git .venv/bin/pip install -q -r requirements.txt && sudo -u git .venv/bin/python manage.py migrate --noinput && sudo -u git .venv/bin/python manage.py collectstatic --noinput --clear 2>/dev/null || true && systemctl restart portpax-api 2>/dev/null || echo ' (service portpax-api not found)'"

echo "[deploy] Done. https://api.portpax.com"
