#!/usr/bin/env bash
#
# One-time DEV API host setup (BCT, api.portpax.com). Run as root on Ubuntu.
# Installs local Postgres + Redis + Nginx + Certbot (all-in-one host).
#
# After this script:
#   1. Clone or rsync backend to /home/git/backend
#   2. cp .env.dev.template .env && fill secrets
#   3. cp config/settings/local_settings.dev.template.py config/settings/local_settings.py
#   4. ./scripts/init_db.sh
#   5. As git: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#   6. ./scripts/install_server_config.sh
#   7. systemctl start portpax-api
#   8. certbot certonly --webroot -w /var/www/letsencrypt -d api.portpax.com
#   9. ./scripts/install_server_config.sh --ssl
#  10. sudo ./scripts/fail2ban/install.sh
#  11. Install systemd units (gunicorn, daphne, celery-worker, tmux) from scripts/systemd/
#
# Subsequent updates: ./scripts/deploy.sh from your machine.
# PRODUCTION bootstrap: ./scripts/setup-prod.sh
#

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root (sudo $0)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "[setup-dev] Updating apt..."
apt-get update -qq

echo "[setup-dev] Installing system packages..."
apt-get install -y \
  postgresql postgresql-contrib \
  redis-server \
  nginx \
  certbot python3-certbot-nginx \
  python3 python3-venv python3-dev python3-pip \
  libpq-dev \
  git \
  rsync \
  fail2ban \
  tmux \
  ccze \
  btop

echo "[setup-dev] Ensuring user git and app directory..."
id git 2>/dev/null || useradd -m -s /bin/bash git
mkdir -p /home/git/backend
chown -R git:git /home/git

echo "[setup-dev] ACME webroot for Let's Encrypt..."
mkdir -p /var/www/letsencrypt
chown -R www-data:www-data /var/www/letsencrypt

echo "[setup-dev] Removing default nginx site (if present)..."
rm -f /etc/nginx/sites-enabled/default

echo "[setup-dev] Done. See header comments for next steps."
