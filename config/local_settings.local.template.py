"""
LOCAL environment — copy to config/local_settings.py

  cp config/local_settings.local.template.py config/local_settings.py
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PORTPAX_ENV = "LOCAL"

SECRET_KEY = "django-insecure-local-only-change-me"
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Optional sandbox credentials (uncomment as needed)
# AWS_ACCESS_KEY_ID = ""
# AWS_SECRET_ACCESS_KEY = ""
# AWS_STORAGE_BUCKET_NAME = ""
# AWS_S3_REGION_NAME = "us-east-1"
# MAILGUN_API_KEY = ""
# MAILGUN_DOMAIN = ""
