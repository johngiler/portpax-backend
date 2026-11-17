"""Stage large booking-id filters for list GET (avoids huge query strings)."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from django.conf import settings

TTL_SECONDS = 60 * 60 * 2
_KEY_RE = re.compile(r"^[0-9a-f]{32}$")


def _filter_dir() -> Path:
    path = Path(settings.BASE_DIR) / "data" / "list_id_filters"
    path.mkdir(parents=True, exist_ok=True)
    return path


def stage_booking_ids(ids: list[int]) -> str:
    """Persist ids and return a 32-char hex key for ?id_filter=."""
    cleaned: list[int] = []
    seen: set[int] = set()
    for raw in ids:
        try:
            bid = int(raw)
        except (TypeError, ValueError):
            continue
        if bid in seen:
            continue
        seen.add(bid)
        cleaned.append(bid)

    key = uuid.uuid4().hex
    payload = {"ids": cleaned, "created_at": time.time()}
    (_filter_dir() / f"{key}.json").write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )
    return key


def resolve_booking_ids(key: str) -> list[int] | None:
    """Load staged ids; returns None if missing/invalid/expired."""
    if not key or not _KEY_RE.match(key):
        return None
    path = _filter_dir() / f"{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    created = data.get("created_at")
    try:
        created_f = float(created)
    except (TypeError, ValueError):
        return None
    if time.time() - created_f > TTL_SECONDS:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    ids_raw = data.get("ids")
    if not isinstance(ids_raw, list):
        return None
    out: list[int] = []
    for raw in ids_raw:
        try:
            out.append(int(raw))
        except (TypeError, ValueError):
            continue
    return out
