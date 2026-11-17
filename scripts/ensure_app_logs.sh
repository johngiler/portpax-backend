#!/usr/bin/env bash
#
# Create API host log files used by systemd units + tmux_ops (run as root).
#   gunicorn.service  → /var/log/gunicorn.log, gunicorn-access.log
#   daphne.service    → /var/log/daphne.log
#   celery-worker     → /var/log/celery.log
#
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root (sudo $0)" >&2
  exit 1
fi

mkdir -p /var/log

LOGS=(
  /var/log/gunicorn.log
  /var/log/gunicorn-access.log
  /var/log/daphne.log
  /var/log/celery.log
)

touch "${LOGS[@]}"
chown git:git "${LOGS[@]}"
chmod 644 "${LOGS[@]}"

echo "[ensure_app_logs] Ready: ${LOGS[*]}"
