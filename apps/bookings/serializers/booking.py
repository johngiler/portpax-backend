from rest_framework import serializers

from apps.audit.models import BookingAuditEntry
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.status import (
    BookingStatusError,
    BookingValidationError,
    update_booking_operational,
    update_booking_status,
)
from apps.bookings.services.validation import validate_booking_params
from apps.catalogs.utils.position_code import position_short_code


class BookingAuditEntrySerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = BookingAuditEntry
        fields = [
            "id",
            "action",
            "summary",
            "changes",
            "user_display",
            "created_at",
        ]

    def get_user_display(self, obj) -> str | None:
        if not obj.user_id:
            return None
        return obj.user.get_username()


class BookingSerializer(serializers.ModelSerializer):
    port_code = serializers.CharField(source="port.code", read_only=True)
    port_name = serializers.CharField(source="port.name", read_only=True)
    port_logo = serializers.SerializerMethodField()
    shipping_line_code = serializers.CharField(source="shipping_line.code", read_only=True)
    shipping_line_name = serializers.CharField(source="shipping_line.name", read_only=True)
    vessel_name = serializers.CharField(source="vessel.name", read_only=True)
    position_code = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    cancellation_evidence_url = serializers.SerializerMethodField()
    confirmation_pdf_url = serializers.SerializerMethodField()
    audit_entries = BookingAuditEntrySerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "booking_code",
            "folio",
            "port",
            "port_code",
            "port_name",
            "port_logo",
            "shipping_line",
            "shipping_line_code",
            "shipping_line_name",
            "vessel",
            "vessel_name",
            "position",
            "position_code",
            "call_date",
            "eta",
            "etd",
            "planned_pax",
            "actual_pax",
            "actual_crew",
            "status",
            "status_display",
            "notes",
            "cancellation_evidence_url",
            "confirmation_pdf_url",
            "audit_entries",
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

    def get_position_code(self, obj: Booking) -> str | None:
        if not obj.position_id:
            return None
        return position_short_code(obj.port.code, obj.position.code)

    def _file_url(self, field) -> str | None:
        if not field:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(field.url)
        return field.url

    def get_cancellation_evidence_url(self, obj) -> str | None:
        return self._file_url(obj.cancellation_evidence)

    def get_confirmation_pdf_url(self, obj) -> str | None:
        return self._file_url(obj.confirmation_pdf)


class BookingUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=BookingStatus.choices,
        required=False,
    )
    position = serializers.IntegerField(required=False, allow_null=True)
    eta = serializers.TimeField(required=False, allow_null=True)
    etd = serializers.TimeField(required=False, allow_null=True)
    planned_pax = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    actual_pax = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    actual_crew = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    cancellation_evidence = serializers.FileField(required=False, allow_null=True)

    def update(self, instance, validated_data):
        user = self.context.get("request").user if self.context.get("request") else None
        cancellation_evidence = validated_data.pop("cancellation_evidence", None)
        new_status = validated_data.pop("status", None)

        if new_status:
            try:
                instance = update_booking_status(
                    instance,
                    new_status,
                    user=user,
                    cancellation_evidence=cancellation_evidence,
                )
            except BookingValidationError as exc:
                raise serializers.ValidationError({"status": exc.errors}) from exc
            except BookingStatusError as exc:
                raise serializers.ValidationError({"status": str(exc)}) from exc

        operational_fields = {}
        for key in ("position", "eta", "etd", "planned_pax", "actual_pax", "actual_crew"):
            if key in validated_data:
                operational_fields[key] = validated_data[key]

        if operational_fields:
            instance = update_booking_operational(
                instance,
                user=user,
                position_id=operational_fields.get("position"),
                eta=operational_fields.get("eta"),
                etd=operational_fields.get("etd"),
                planned_pax=operational_fields.get("planned_pax"),
                actual_pax=operational_fields.get("actual_pax"),
                actual_crew=operational_fields.get("actual_crew"),
            )

        return instance


class BookingValidateSerializer(serializers.Serializer):
    port = serializers.IntegerField()
    vessel = serializers.IntegerField()
    call_dates = serializers.ListField(child=serializers.DateField(), allow_empty=False)
    position = serializers.IntegerField(required=False, allow_null=True)

    def validate_call_dates(self, value):
        unique = sorted({d for d in value})
        if len(unique) != len(value):
            raise serializers.ValidationError("Las fechas deben ser únicas.")
        return unique

    def create(self, validated_data):
        return validate_booking_params(
            port_id=validated_data["port"],
            vessel_id=validated_data["vessel"],
            call_dates=validated_data["call_dates"],
            position_id=validated_data.get("position"),
        )


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
