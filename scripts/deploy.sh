#!/usr/bin/env bash
#
# Deploy PortPax backend to api.portpax.com (portpax-api).
# Requires: rsync, SSH config Host portpax-api -> api.portpax.com, root on remote.
# Target: /home/git/backend (gunicorn :8000 HTTP, daphne :8001 WebSockets).
#
# Server-only files (never overwritten by rsync):
#   .env, config/settings/local_settings.py, .venv, db.sqlite3, media/, data/, staticfiles/
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
  --exclude ".git"
  --exclude "media/"
  --exclude "data/"
  --exclude "staticfiles/"
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

echo "[deploy] Restarting gunicorn.service..."
if ssh "$REMOTE_HOST" "systemctl is-enabled gunicorn.service >/dev/null 2>&1"; then
  ssh "$REMOTE_HOST" "sudo bash $REMOTE_PATH/scripts/ensure_gunicorn_logs.sh"
  ssh "$REMOTE_HOST" "systemctl restart gunicorn.service"
else
  echo "[deploy] WARN: gunicorn.service systemd unit not installed. On server run:"
  echo "cp scripts/systemd/gunicorn.service /etc/systemd/system/gunicorn.service"
  echo "systemctl daemon-reload"
  echo "systemctl enable gunicorn.service"
  echo "systemctl start gunicorn.service"
fi

echo "[deploy] Restarting daphne.service (WebSockets)..."
if ssh "$REMOTE_HOST" "systemctl is-enabled daphne.service >/dev/null 2>&1"; then
  ssh "$REMOTE_HOST" "sudo bash $REMOTE_PATH/scripts/ensure_daphne_logs.sh"
  ssh "$REMOTE_HOST" "systemctl restart daphne.service"
else
  echo "[deploy] WARN: daphne.service not installed. On server run:"
  echo "cp scripts/systemd/daphne.service /etc/systemd/system/daphne.service"
  echo "systemctl daemon-reload && systemctl enable --now daphne.service"
  echo "Update nginx site from scripts/nginx/api.portpax.com.conf (location /ws/) and reload nginx."
fi

if ssh "$REMOTE_HOST" "systemctl is-active nginx >/dev/null 2>&1"; then
  ssh "$REMOTE_HOST" "systemctl reload nginx"
fi

# Celery worker — optional restart (default: no)
read -r -p "[deploy] ¿Reiniciar celery? [y/N] " RESTART_CELERY
if [[ "${RESTART_CELERY}" =~ ^[yY]$ ]]; then
  echo "[deploy] Restarting celery-worker.service..."
  if ssh "$REMOTE_HOST" "systemctl is-enabled celery-worker.service >/dev/null 2>&1"; then
    ssh "$REMOTE_HOST" "systemctl restart celery-worker.service"
  else
    echo "[deploy] WARN: celery-worker.service not installed. On server run:"
    echo "cp scripts/systemd/celery-worker.service /etc/systemd/system/celery-worker.service"
    echo "systemctl daemon-reload && systemctl enable --now celery-worker.service"
  fi
else
  echo "[deploy] Celery worker left running (no restart)."
fi

echo "[deploy] Done. https://api.portpax.com/api/health/"
