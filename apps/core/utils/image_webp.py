import io
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image

DEFAULT_WEBP_QUALITY = 85


def convert_uploaded_image_to_webp(
    uploaded_file,
    *,
    quality: int = DEFAULT_WEBP_QUALITY,
) -> ContentFile:
    """Convert an uploaded image to WebP for smaller storage with good quality."""
    uploaded_file.seek(0)
    with Image.open(uploaded_file) as img:
        if getattr(img, "is_animated", False):
            img.seek(0)

        has_alpha = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )
        img = img.convert("RGBA" if has_alpha else "RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=quality, method=6)

    stem = Path(getattr(uploaded_file, "name", "") or "image").stem or "image"
    return ContentFile(buffer.getvalue(), name=f"{stem}.webp")
