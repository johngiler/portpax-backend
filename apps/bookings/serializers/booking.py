from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.status import BookingStatusError, update_booking_status


class BookingSerializer(serializers.ModelSerializer):
    port_code = serializers.CharField(source="port.code", read_only=True)
    port_name = serializers.CharField(source="port.name", read_only=True)
    port_logo = serializers.SerializerMethodField()
    shipping_line_code = serializers.CharField(source="shipping_line.code", read_only=True)
    shipping_line_name = serializers.CharField(source="shipping_line.name", read_only=True)
    vessel_name = serializers.CharField(source="vessel.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_code",
            "port",
            "port_code",
            "port_name",
            "port_logo",
            "shipping_line",
            "shipping_line_code",
            "shipping_line_name",
            "vessel",
            "vessel_name",
            "call_date",
            "status",
            "status_display",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_port_logo(self, obj) -> str | None:
        logo = obj.port.logo
        if not logo:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(logo.url)
        return logo.url


class BookingStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ["status"]

    def validate_status(self, value):
        booking = self.instance
        if booking and value == booking.status:
            raise serializers.ValidationError("El estado ya es el mismo.")
        return value

    def update(self, instance, validated_data):
        new_status = validated_data["status"]
        try:
            return update_booking_status(instance, new_status)
        except BookingStatusError as exc:
            raise serializers.ValidationError({"status": str(exc)}) from exc


class BookingBatchCreateSerializer(serializers.Serializer):
    port = serializers.IntegerField()
    shipping_line = serializers.IntegerField()
    vessel = serializers.IntegerField()
    call_dates = serializers.ListField(
        child=serializers.DateField(),
        allow_empty=False,
        max_length=60,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_call_dates(self, value):
        if not value:
            raise serializers.ValidationError("Selecciona al menos una fecha.")
        unique = sorted({d for d in value})
        if len(unique) != len(value):
            raise serializers.ValidationError("Las fechas deben ser únicas.")
        return unique
