"""
LOCAL environment — copy to config/settings/local_settings.py

  cp config/settings/local_settings.local.template.py config/settings/local_settings.py

Requires backend/.env (see .env.local.template) and local Postgres:
  docker-compose up -d
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

PORTPAX_ENV = "LOCAL"

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-local-only-change-me",
)
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# Optional sandbox credentials (uncomment as needed)
# AWS_ACCESS_KEY_ID = ""
# AWS_SECRET_ACCESS_KEY = ""
# AWS_STORAGE_BUCKET_NAME = ""
# AWS_S3_REGION_NAME = "us-east-1"
# MAILGUN_API_KEY = ""
# MAILGUN_DOMAIN = ""
