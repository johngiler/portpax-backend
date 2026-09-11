"""PortPax Django settings package. Loaded via DJANGO_SETTINGS_MODULE=config.settings."""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403

try:
    from .local_settings import *  # noqa: F403
except ImportError as exc:
    raise ImproperlyConfigured(
        "config/settings/local_settings.py is required. "
        "Copy config/settings/local_settings.local.template.py or the matching "
        "local_settings.<env>.template.py for your environment."
    ) from exc

# Re-read after local_settings load_dotenv (settings.py runs before .env is loaded).
FRONTEND_BUILD_PUBLISH_TOKEN = os.environ.get("FRONTEND_BUILD_PUBLISH_TOKEN", "")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", CELERY_BROKER_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_RESULT_BACKEND)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [CELERY_BROKER_URL],
        },
    },
}
