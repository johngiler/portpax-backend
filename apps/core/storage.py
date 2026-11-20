"""Media storage backends.

LOCAL/DEV: Django default FileSystemStorage (MEDIA_ROOT).
PRODUCTION: MediaS3Storage — same relative keys as MEDIA_ROOT, public URLs
stay under MEDIA_URL (/media/...) so nginx can proxy to the app.
"""

from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage
from storages.utils import clean_name


class MediaS3Storage(S3Boto3Storage):
    """S3 object store with API-relative media URLs.

    Object keys mirror on-disk paths (shipping_lines/logos/..., bookings/...).
    .url() returns /media/<key> so serializers keep build_absolute_uri →
    https://api…/media/... (nginx proxies that path to Django → S3).
    """

    def url(
        self,
        name: str,
        parameters: dict | None = None,
        expire: int | None = None,
        http_method: str | None = None,
    ) -> str:
        del parameters, expire, http_method  # signed S3 URLs not used in API payloads
        cleaned = self._normalize_name(clean_name(name))
        base = settings.MEDIA_URL
        if not base.endswith("/"):
            base = f"{base}/"
        # urljoin drops the media prefix if cleaned is absolute-looking; keep join safe.
        return urljoin(base, cleaned.lstrip("/"))
