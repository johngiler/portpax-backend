"""PortPax Django settings package. Loaded via DJANGO_SETTINGS_MODULE=config.settings."""

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
