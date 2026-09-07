from rest_framework import serializers

from apps.bookings.models import BookingTag
from apps.bookings.services.booking_tag import normalize_tag_name


class BookingTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingTag
        fields = ["id", "name", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value: str) -> str:
        cleaned = normalize_tag_name(value)
        if not cleaned:
            raise serializers.ValidationError("Requerido.")
        qs = BookingTag.objects.filter(name__iexact=cleaned)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un tag con ese nombre.")
        return cleaned

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and getattr(request.user, "is_authenticated", False) else None
        return BookingTag.objects.create(
            name=validated_data["name"],
            created_by=user,
        )
