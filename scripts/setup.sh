#!/usr/bin/env bash
#
# One-time server setup for PortPax API (Ubuntu). Run as root on api.portpax.com.
# Installs: Postgres, Nginx, Certbot, Python venv deps.
#
# After this script, on the server:
#   1. Clone or rsync backend to /home/git/backend
#   2. cp .env.dev.template .env && fill secrets
#   3. cp config/settings/local_settings.dev.template.py config/settings/local_settings.py
#   4. ./scripts/init_db.sh
#   5. As git: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#   6. ./scripts/install_server_config.sh
#   7. systemctl start portpax-api
#   8. certbot certonly --webroot -w /var/www/letsencrypt -d api.portpax.com
#   9. ./scripts/install_server_config.sh --ssl
#
# From your machine: ./scripts/deploy.sh for subsequent updates.
#

set -e

export DEBIAN_FRONTEND=noninteractive

echo "[setup] Updating apt..."
apt-get update -qq

echo "[setup] Installing system packages..."
apt-get install -y \
  postgresql postgresql-contrib \
  nginx \
  certbot python3-certbot-nginx \
  python3 python3-venv python3-dev python3-pip \
  libpq-dev \
  git \
  rsync

echo "[setup] Ensuring user git and app directory..."
id git 2>/dev/null || useradd -m -s /bin/bash git
mkdir -p /home/git/backend
chown -R git:git /home/git

echo "[setup] ACME webroot for Let's Encrypt..."
mkdir -p /var/www/letsencrypt
chown -R www-data:www-data /var/www/letsencrypt

echo "[setup] Removing default nginx site (if present)..."
rm -f /etc/nginx/sites-enabled/default

echo "[setup] Done. See header comments in this script for next steps."
