#!/usr/bin/env bash
# Create Daphne log file (run as root on the API server once, or from deploy).
set -e

touch /var/log/daphne.log
chown git:git /var/log/daphne.log
chmod 644 /var/log/daphne.log

echo "Daphne log: /var/log/daphne.log"
