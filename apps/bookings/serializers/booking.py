from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus


class BookingSerializer(serializers.ModelSerializer):
    port_code = serializers.CharField(source="port.code", read_only=True)
    port_name = serializers.CharField(source="port.name", read_only=True)
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
