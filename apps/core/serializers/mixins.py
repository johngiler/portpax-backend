from apps.core.utils.image_webp import convert_uploaded_image_to_webp


class WebPImageFieldsMixin:
    """Convert configured image fields to WebP on create/update."""

    webp_image_fields: tuple[str, ...] = ()

    def _apply_webp(self, validated_data: dict) -> None:
        for field in self.webp_image_fields:
            if field in validated_data and validated_data[field] is not None:
                validated_data[field] = convert_uploaded_image_to_webp(validated_data[field])

    def create(self, validated_data):
        self._apply_webp(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._apply_webp(validated_data)
        return super().update(instance, validated_data)
