#!/usr/bin/env bash
#
# PRODUCTION API host — pull a release from S3 into /home/git/backend.
# Invoked by GitHub Actions via SSM SendCommand (or manually as root).
#
# Always: sync code, pip, check, migrate, collectstatic, restart gunicorn, reload nginx.
# Optional: --restart-daphne / --restart-celery (WebSockets / async workers).
#
# Preserves server-only files: .env, local_settings.py, .venv, media/, data/, staticfiles/
#
# Usage:
#   sudo ./scripts/deploy-prod-from-s3.sh s3://…/backend/<sha>/
#   sudo ./scripts/deploy-prod-from-s3.sh s3://…/backend/<sha>/ --restart-daphne --restart-celery
#
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root (sudo $0 <s3-uri> [--restart-daphne] [--restart-celery])" >&2
  exit 1
fi

S3_URI=""
RESTART_DAPHNE=0
RESTART_CELERY=0

for arg in "$@"; do
  case "$arg" in
    --restart-daphne) RESTART_DAPHNE=1 ;;
    --restart-celery) RESTART_CELERY=1 ;;
    -h|--help)
      echo "Usage: $0 <s3-uri> [--restart-daphne] [--restart-celery]"
      echo "  Always restarts gunicorn; migrate + collectstatic + pip."
      exit 0
      ;;
    s3://*)
      S3_URI="$arg"
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: $0 <s3-uri> [--restart-daphne] [--restart-celery]" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$S3_URI" ]]; then
  echo "Usage: $0 <s3-uri> [--restart-daphne] [--restart-celery]" >&2
  exit 2
fi

APP_ROOT="/home/git/backend"
TMP_DIR="$(mktemp -d /tmp/portpax-backend-XXXXXX)"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

echo "[deploy-prod] Syncing ${S3_URI} → ${TMP_DIR}"
aws s3 sync "$S3_URI" "$TMP_DIR" --delete --region us-east-1

if [[ ! -f "${TMP_DIR}/manage.py" ]]; then
  echo "ERROR: release missing manage.py" >&2
  exit 1
fi

if [[ ! -f "${APP_ROOT}/.env" ]]; then
  echo "ERROR: ${APP_ROOT}/.env missing (server-only; not in release)" >&2
  exit 1
fi
if [[ ! -f "${APP_ROOT}/config/settings/local_settings.py" ]]; then
  echo "ERROR: local_settings.py missing (server-only; not in release)" >&2
  exit 1
fi

echo "[deploy-prod] Publishing code → ${APP_ROOT}"
rsync -a --delete \
  --exclude ".venv/" \
  --exclude ".env" \
  --exclude "config/settings/local_settings.py" \
  --exclude "db.sqlite3" \
  --exclude ".git/" \
  --exclude "media/" \
  --exclude "data/" \
  --exclude "staticfiles/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  "${TMP_DIR}/" "${APP_ROOT}/"

chown -R git:git "$APP_ROOT"

if [[ ! -d "${APP_ROOT}/.venv" ]]; then
  echo "[deploy-prod] Creating venv..."
  sudo -u git python3 -m venv "${APP_ROOT}/.venv"
fi

echo "[deploy-prod] pip + check + migrate + collectstatic"
sudo -u git "${APP_ROOT}/.venv/bin/pip" install -q -r "${APP_ROOT}/requirements.txt"
sudo -u git "${APP_ROOT}/.venv/bin/python" "${APP_ROOT}/manage.py" check
sudo -u git "${APP_ROOT}/.venv/bin/python" "${APP_ROOT}/manage.py" migrate --noinput
sudo -u git "${APP_ROOT}/.venv/bin/python" "${APP_ROOT}/manage.py" collectstatic --noinput --clear 2>/dev/null || true

restart_unit() {
  local unit="$1"
  if systemctl is-enabled "$unit" >/dev/null 2>&1; then
    echo "[deploy-prod] Restarting ${unit}"
    systemctl restart "$unit"
  else
    echo "[deploy-prod] WARN: ${unit} not enabled — skip"
  fi
}

if [[ -x "${APP_ROOT}/scripts/ensure_app_logs.sh" ]]; then
  bash "${APP_ROOT}/scripts/ensure_app_logs.sh" || true
fi
if [[ -x "${APP_ROOT}/scripts/ensure_gunicorn_logs.sh" ]]; then
  bash "${APP_ROOT}/scripts/ensure_gunicorn_logs.sh" || true
fi

# Always restart HTTP API
restart_unit gunicorn.service

if [[ "$RESTART_DAPHNE" -eq 1 ]]; then
  if [[ -x "${APP_ROOT}/scripts/ensure_daphne_logs.sh" ]]; then
    bash "${APP_ROOT}/scripts/ensure_daphne_logs.sh" || true
  fi
  restart_unit daphne.service
else
  echo "[deploy-prod] Daphne left running (no --restart-daphne)"
fi

if [[ "$RESTART_CELERY" -eq 1 ]]; then
  restart_unit celery-worker.service
else
  echo "[deploy-prod] Celery left running (no --restart-celery)"
fi

if systemctl is-active nginx >/dev/null 2>&1; then
  systemctl reload nginx
fi

echo "[deploy-prod] Done. gunicorn restarted; daphne=${RESTART_DAPHNE} celery=${RESTART_CELERY}"
