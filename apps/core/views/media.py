"""Serve media via default_storage (filesystem locally; S3 in PRODUCTION)."""

from __future__ import annotations

import mimetypes

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpRequest, HttpResponse


def serve_media(request: HttpRequest, path: str) -> HttpResponse:
    """Stream a media object. Used in PRODUCTION when nginx proxies /media/ here."""
    del request
    if not path or path.endswith("/") or ".." in path.split("/"):
        raise Http404
    if not default_storage.exists(path):
        raise Http404

    content_type, _ = mimetypes.guess_type(path)
    handle = default_storage.open(path, "rb")
    response = FileResponse(
        handle,
        content_type=content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "public, max-age=604800"
    return response
