#!/usr/bin/env bash
#
# One-time PRODUCTION API host setup (ITM AWS EC2). Run as root via Session Manager.
# RDS Postgres, ElastiCache Redis, S3, and ALB TLS are external — not installed here.
#
# After this script:
#   1. Place backend at /home/git/backend (clone, release artifact, or Actions/SSM)
#   2. Fill Secrets Manager portpax/prod/app (and/or .env from .env.production.template)
#   3. cp config/settings/local_settings.production.template.py \
#        config/settings/local_settings.py
#   4. As git: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
#   5. Install nginx site + systemd: gunicorn, daphne, celery-worker
#      (ALB health check expects HTTP 200 on :80 /)
#   6. sudo ./scripts/fail2ban/install.sh
#      then disable the sshd jail (prod has no SSH; Session Manager only):
#        rm -f /etc/fail2ban/jail.d/sshd-port.local && systemctl restart fail2ban
#   7. cp scripts/systemd/tmux.service /etc/systemd/system/tmux.service
#      systemctl daemon-reload && systemctl enable --now tmux.service
#   8. migrate / collectstatic / create app DB user (not portpax_admin)
#
# DEV bootstrap: ./scripts/setup-dev.sh
#

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root (sudo $0)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_awscli_v2() {
  if command -v aws >/dev/null 2>&1; then
    echo "[setup-prod] awscli already present: $(aws --version 2>&1)"
    return 0
  fi
  echo "[setup-prod] Installing AWS CLI v2..."
  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" \
    -o "${tmp}/awscliv2.zip"
  unzip -q "${tmp}/awscliv2.zip" -d "${tmp}"
  "${tmp}/aws/install"
  rm -rf "${tmp}"
}

# RDS is Postgres 17; Ubuntu's default client is 16 and breaks psql meta-commands (\l).
install_psql_client_17() {
  echo "[setup-prod] Installing PostgreSQL 17 client (PGDG)..."
  apt-get install -y curl ca-certificates
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc
  . /etc/os-release
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
    >/etc/apt/sources.list.d/pgdg.list
  apt-get update -qq
  apt-get install -y postgresql-client-17
  if [[ -x /usr/lib/postgresql/17/bin/psql ]]; then
    update-alternatives --install /usr/bin/psql psql /usr/lib/postgresql/17/bin/psql 170
  fi
  echo "[setup-prod] psql: $(psql --version)"
}

echo "[setup-prod] Updating apt..."
apt-get update -qq

echo "[setup-prod] Installing system packages..."
apt-get install -y \
  nginx \
  python3 python3-venv python3-dev python3-pip \
  libpq-dev \
  git \
  rsync \
  curl \
  unzip \
  ca-certificates \
  fail2ban \
  tmux \
  ccze \
  btop

install_psql_client_17
install_awscli_v2

echo "[setup-prod] Ensuring user git and app directory..."
id git 2>/dev/null || useradd -m -s /bin/bash git
mkdir -p /home/git/backend
chown -R git:git /home/git

echo "[setup-prod] Removing default nginx site (if present)..."
rm -f /etc/nginx/sites-enabled/default

if [[ -x "${SCRIPT_DIR}/fail2ban/install.sh" ]]; then
  echo "[setup-prod] Installing PortPax fail2ban jails..."
  "${SCRIPT_DIR}/fail2ban/install.sh"
  # Prod access is Session Manager only; BCT sshd:2200 jail does not apply.
  rm -f /etc/fail2ban/jail.d/sshd-port.local
  systemctl restart fail2ban
else
  echo "[setup-prod] fail2ban package installed; run scripts/fail2ban/install.sh after code is on disk."
fi

echo "[setup-prod] Done. See header comments for next steps."
