"""Build channels_redis hosts from the Celery broker URL.

redis-py (asyncio) accepts ssl_cert_reqs=none|optional|required.
Celery/kombu also accepts CERT_NONE; normalize so Daphne can use rediss://.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_CERT_REQS_ALIASES = {
    "CERT_NONE": "none",
    "CERT_OPTIONAL": "optional",
    "CERT_REQUIRED": "required",
}


def channel_layer_hosts(broker_url: str) -> list[dict[str, Any]]:
    """Return channels_redis CONFIG hosts for a redis:// or rediss:// URL."""
    if not broker_url:
        return [{"address": "redis://localhost:6379/0"}]

    parsed = urlparse(broker_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    cert = query.get("ssl_cert_reqs")
    if cert in _CERT_REQS_ALIASES:
        query["ssl_cert_reqs"] = _CERT_REQS_ALIASES[cert]

    clean = urlunparse(parsed._replace(query=urlencode(query)))
    return [{"address": clean}]
