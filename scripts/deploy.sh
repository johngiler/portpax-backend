#!/usr/bin/env bash
#
# Deploy PortPax backend to api.portpax.com (portpax-api).
# Requires: rsync, SSH config Host portpax-api -> api.portpax.com, root on remote.
# Target: /home/git/backend (gunicorn via systemd unit portpax-api).
#
# Server-only files (never overwritten by rsync):
#   .env, config/settings/local_settings.py, .venv, db.sqlite3, staticfiles/
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REMOTE_HOST="portpax-api"
REMOTE_PATH="/home/git/backend"

RSYNC_EXCLUDE=(
  --exclude ".venv"
  --exclude "__pycache__"
  --exclude "*.pyc"
  --exclude ".env"
  --exclude "config/settings/local_settings.py"
  --exclude "db.sqlite3"
  --exclude "staticfiles"
  --exclude ".git"
)

cd "$BACKEND_DIR"

echo "[deploy] Syncing backend -> $REMOTE_HOST:$REMOTE_PATH"
rsync -avz --delete "${RSYNC_EXCLUDE[@]}" -e ssh "$BACKEND_DIR/" "$REMOTE_HOST:$REMOTE_PATH/"

REMOTE_SETUP="
set -e
chown -R git:git $REMOTE_PATH
cd $REMOTE_PATH

if [[ ! -f .env ]]; then
  echo 'ERROR: $REMOTE_PATH/.env missing. Copy .env.dev.template to .env on the server.' >&2
  exit 1
fi
if [[ ! -f config/settings/local_settings.py ]]; then
  echo 'ERROR: config/settings/local_settings.py missing. Copy local_settings.dev.template.py on the server.' >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo '[deploy] Creating Python venv...'
  sudo -u git python3 -m venv .venv
fi

sudo -u git .venv/bin/pip install -q -r requirements.txt
sudo -u git .venv/bin/python manage.py check
sudo -u git .venv/bin/python manage.py migrate --noinput
sudo -u git .venv/bin/python manage.py collectstatic --noinput --clear 2>/dev/null || true
"

echo "[deploy] Remote: venv, migrate, collectstatic..."
ssh "$REMOTE_HOST" "$REMOTE_SETUP"

echo "[deploy] Restarting portpax-api..."
if ssh "$REMOTE_HOST" "systemctl is-enabled portpax-api >/dev/null 2>&1"; then
  ssh "$REMOTE_HOST" "systemctl restart portpax-api && systemctl reload nginx"
else
  echo "[deploy] WARN: portpax-api systemd unit not installed. On server run:"
  echo "  cd $REMOTE_PATH && ./scripts/install_server_config.sh"
fi

echo "[deploy] Done. https://api.portpax.com/api/health/"
