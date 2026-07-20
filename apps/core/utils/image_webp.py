import io
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

DEFAULT_WEBP_QUALITY = 85
# Long edge cap — keeps gallery quality while avoiding multi‑MP RAM spikes on small servers.
MAX_IMAGE_EDGE_PX = 2560
# 4 = balanced encode speed; 6 can exceed gunicorn timeout on large uploads.
WEBP_METHOD = 4

# ~40 MP — reject decompression bombs before full decode.
MAX_IMAGE_PIXELS = 40_000_000

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

UNSUPPORTED_IMAGE_MESSAGE = (
    "Formato de imagen no soportado. Usa JPG, PNG o WebP (no SVG)."
)


class ImageConversionError(Exception):
    """Raised when an upload cannot be converted to WebP."""

    def __init__(self, message: str = UNSUPPORTED_IMAGE_MESSAGE):
        self.message = message
        super().__init__(message)


def _is_svg_upload(uploaded_file) -> bool:
    name = (getattr(uploaded_file, "name", "") or "").lower()
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    return name.endswith(".svg") or "svg" in content_type


def convert_uploaded_image_to_webp(
    uploaded_file,
    *,
    quality: int = DEFAULT_WEBP_QUALITY,
    max_edge: int = MAX_IMAGE_EDGE_PX,
) -> ContentFile:
    """Convert an uploaded image to WebP for smaller storage with good quality."""
    if _is_svg_upload(uploaded_file):
        raise ImageConversionError(UNSUPPORTED_IMAGE_MESSAGE)

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as img:
            if getattr(img, "is_animated", False):
                img.seek(0)

            img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

            has_alpha = img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            )
            img = img.convert("RGBA" if has_alpha else "RGB")

            buffer = io.BytesIO()
            img.save(buffer, format="WEBP", quality=quality, method=WEBP_METHOD)
    except UnidentifiedImageError as exc:
        raise ImageConversionError(UNSUPPORTED_IMAGE_MESSAGE) from exc

    stem = Path(getattr(uploaded_file, "name", "") or "image").stem or "image"
    return ContentFile(buffer.getvalue(), name=f"{stem}.webp")
