#!/usr/bin/env bash
#
# One-time server setup for PortPax API (Ubuntu). Run as root on api.portpax.com.
# Installs: Postgres, Nginx, Certbot, Python venv + system deps for Django/psycopg.
#
# After this: copy backend to /home/git/backend, create .env, run init_db.sh, then deploy.
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
  git

echo "[setup] Ensuring user git and directory..."
id git 2>/dev/null || useradd -m -s /bin/bash git
mkdir -p /home/git/backend
chown -R git:git /home/git

echo "[setup] Allowing nginx to read letsencrypt challenges..."
mkdir -p /var/www/letsencrypt
chown -R www-data:www-data /var/www/letsencrypt

echo "[setup] Done. Next steps:"
echo "  1. Copy backend code to /home/git/backend (or clone)"
echo "  2. Copy .env to /home/git/backend/.env"
echo "  3. Run init_db.sh (as postgres or root) to create DB"
echo "  4. As git: cd /home/git/backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
echo "  5. Deploy nginx config and run certbot, then deploy.sh / systemd"
