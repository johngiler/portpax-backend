#!/usr/bin/env bash
# Create Gunicorn log files (run as root on the API server once, or from deploy).
set -e

touch /var/log/gunicorn.log /var/log/gunicorn-access.log
chown git:git /var/log/gunicorn.log /var/log/gunicorn-access.log
chmod 644 /var/log/gunicorn.log /var/log/gunicorn-access.log

echo "Gunicorn logs: /var/log/gunicorn.log (errors), /var/log/gunicorn-access.log (access)"
