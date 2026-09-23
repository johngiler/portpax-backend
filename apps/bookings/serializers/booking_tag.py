from rest_framework import serializers

from apps.bookings.models import BookingTag
from apps.bookings.services.booking_tag import normalize_tag_name


class BookingTagSerializer(serializers.ModelSerializer):
    booking_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = BookingTag
        fields = ["id", "name", "booking_count", "created_at"]
        read_only_fields = ["id", "booking_count", "created_at"]

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

    def update(self, instance, validated_data):
        from apps.bookings.services.booking_tag import record_tag_rename_on_bookings

        request = self.context.get("request")
        user = (
            request.user
            if request and getattr(request.user, "is_authenticated", False)
            else None
        )
        previous_name = instance.name
        instance = super().update(instance, validated_data)
        next_name = instance.name
        if previous_name != next_name:
            record_tag_rename_on_bookings(
                instance,
                previous_name=previous_name,
                next_name=next_name,
                user=user,
                request=request,
            )
        return instance
