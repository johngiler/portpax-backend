"""Load a port logo for PDF (ReportLab) and Excel (openpyxl)."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from django.core.files.storage import default_storage
from reportlab.lib.utils import ImageReader


def port_logo_png_bytes(port) -> bytes | None:
    if port is None or not getattr(port, "logo", None):
        return None
    return logo_field_png_bytes(port.logo)


def logo_field_png_bytes(field: Any) -> bytes | None:
    raw = _read_logo_bytes(field)
    if not raw:
        return None
    head = raw[:400].lstrip()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return None
    return _as_png_bytes(raw)


def logo_png_from_assets(
    *, path: str | None = None, name: str | None = None
) -> bytes | None:
    raw: bytes | None = None
    if path:
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError:
            raw = None
    if raw is None and name:
        try:
            with default_storage.open(name, "rb") as handle:
                raw = handle.read()
        except Exception:
            raw = None
    if not raw:
        return None
    head = raw[:400].lstrip()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return None
    return _as_png_bytes(raw)


def port_logo_reader(port) -> ImageReader | None:
    png = port_logo_png_bytes(port)
    if not png:
        return None
    try:
        return ImageReader(BytesIO(png))
    except Exception:
        return None


def add_worksheet_logo(
    ws,
    png: bytes | None,
    *,
    row: int = 1,
    col: int = 1,
    max_w: int = 108,
    max_h: int = 48,
) -> bool:
    """Anchor a PNG on an Excel sheet. Keeps the buffer alive until save."""
    if not png:
        return False
    try:
        from openpyxl.drawing.image import Image as XLImage
        from openpyxl.utils import get_column_letter
    except Exception:
        return False
    buf = BytesIO(png)
    buf.name = "port-logo.png"
    try:
        image = XLImage(buf)
    except Exception:
        return False
    width = float(image.width or 1)
    height = float(image.height or 1)
    scale = min(max_w / width, max_h / height)
    image.width = max(1, int(width * scale))
    image.height = max(1, int(height * scale))
    image.anchor = f"{get_column_letter(col)}{row}"
    ws.add_image(image)
    held = getattr(ws, "_logo_buffers", None)
    if held is None:
        held = []
        ws._logo_buffers = held
    held.append(buf)
    return True


def add_worksheet_port_logo(
    ws,
    port,
    *,
    row: int = 1,
    col: int = 1,
    max_w: int = 108,
    max_h: int = 48,
) -> bool:
    return add_worksheet_logo(
        ws, port_logo_png_bytes(port), row=row, col=col, max_w=max_w, max_h=max_h
    )


def load_ports_by_ids(ids) -> list:
    from apps.catalogs.models import Port

    ordered: list[int] = []
    for raw in ids or []:
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid > 0 and pid not in ordered:
            ordered.append(pid)
    if not ordered:
        return []
    found = {item.id: item for item in Port.objects.filter(id__in=ordered)}
    return [found[pid] for pid in ordered if pid in found]


def unique_banner_ports(ports) -> list:
    """At most one Port for a global banner. Never a collage of logos."""
    seen: list = []
    keys: set = set()
    for port in ports or []:
        if port is None:
            continue
        key = getattr(port, "pk", None)
        if key is None:
            key = id(port)
        if key in keys:
            continue
        keys.add(key)
        seen.append(port)
    return seen if len(seen) == 1 else []


def ports_from_report_payload(payload: dict | None) -> list:
    """Banner logo only when the export is scoped to one unique port."""
    data = payload or {}
    if data.get("port_id"):
        return unique_banner_ports(load_ports_by_ids([data["port_id"]]))
    port = data.get("port")
    if isinstance(port, dict) and port.get("id"):
        return unique_banner_ports(load_ports_by_ids([port["id"]]))
    return []


def _read_logo_bytes(field: Any) -> bytes | None:
    try:
        path = field.path
        if path:
            with open(path, "rb") as handle:
                return handle.read()
    except Exception:
        pass
    name = getattr(field, "name", None)
    if not name:
        return None
    try:
        with default_storage.open(name, "rb") as handle:
            return handle.read()
    except Exception:
        return None


def _as_png_bytes(raw: bytes) -> bytes | None:
    try:
        from PIL import Image as PILImage

        image = PILImage.open(BytesIO(raw))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return raw
