"""
PRODUCTION environment (ITM AWS) — copy to config/settings/local_settings.py
on the API EC2 (api.portpax.itmgroup.mx).

  cp config/settings/local_settings.production.template.py \
     config/settings/local_settings.py

Requires backend/.env (see .env.production.template) and/or the same keys in
Secrets Manager secret portpax/prod/app.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

PORTPAX_ENV = "PRODUCTION"

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False

# ALB terminates TLS and forwards HTTP to :80 with X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "api.portpax.itmgroup.mx").split(",")
    if h.strip()
]

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "https://portpax.itmgroup.mx",
    ).split(",")
    if o.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CSRF_TRUSTED_ORIGINS",
        "https://portpax.itmgroup.mx,https://api.portpax.itmgroup.mx",
    ).split(",")
    if o.strip()
]

# RDS requires TLS. Keep the CA bundle outside the repo (e.g. /home/git/certs/).
_RDS_SSLROOT = os.environ.get(
    "POSTGRES_SSLROOTCERT",
    "/home/git/certs/rds-global-bundle.pem",
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ["POSTGRES_HOST"],
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "OPTIONS": {
            "sslmode": os.environ.get("POSTGRES_SSLMODE", "verify-full"),
            "sslrootcert": _RDS_SSLROOT,
        },
    }
}

# Prefer the EC2 instance role; set keys only if IAM user credentials are required.
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_STORAGE_BUCKET_NAME = os.environ.get(
    "AWS_STORAGE_BUCKET_NAME",
    "itm-portpax-prod-files-040105284691",
)
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")

MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY", "")
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN", "")
