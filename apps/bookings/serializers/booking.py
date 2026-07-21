from rest_framework import serializers

from apps.audit.models import BookingAuditEntry
from apps.bookings.models import Booking, BookingStatus, CancellationReason
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
    shipping_line_logo = serializers.SerializerMethodField()
    vessel_name = serializers.CharField(source="vessel.name", read_only=True)
    vessel_logo = serializers.SerializerMethodField()
    vessel_loa_m = serializers.DecimalField(
        source="vessel.loa_m",
        max_digits=6,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )
    position_code = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    cancellation_reason = serializers.CharField(read_only=True)
    cancellation_reason_display = serializers.CharField(
        source="get_cancellation_reason_display",
        read_only=True,
    )
    cancellation_evidence_url = serializers.SerializerMethodField()
    confirmation_pdf_url = serializers.SerializerMethodField()
    audit_entries = BookingAuditEntrySerializer(many=True, read_only=True)

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
            "shipping_line_logo",
            "vessel",
            "vessel_name",
            "vessel_logo",
            "vessel_loa_m",
            "position",
            "position_code",
            "call_date",
            "eta",
            "etd",
            "eta_real",
            "etd_real",
            "planned_pax",
            "actual_pax",
            "actual_crew",
            "status",
            "status_display",
            "notes",
            "cancellation_reason",
            "cancellation_reason_display",
            "cancellation_evidence_url",
            "confirmation_pdf_url",
            "audit_entries",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _file_url(self, field) -> str | None:
        if not field:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(field.url)
        return field.url

    def get_port_logo(self, obj) -> str | None:
        return self._file_url(obj.port.logo)

    def get_shipping_line_logo(self, obj) -> str | None:
        return self._file_url(obj.shipping_line.logo)

    def get_vessel_logo(self, obj) -> str | None:
        return self._file_url(obj.vessel.logo)

    def get_position_code(self, obj: Booking) -> str | None:
        if not obj.position_id:
            return None
        return position_short_code(obj.port.code, obj.position.code)

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
    eta_real = serializers.TimeField(required=False, allow_null=True)
    etd_real = serializers.TimeField(required=False, allow_null=True)
    planned_pax = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    actual_pax = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    actual_crew = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    cancellation_reason = serializers.ChoiceField(
        choices=CancellationReason.choices,
        required=False,
        allow_blank=True,
    )
    cancellation_evidence = serializers.FileField(required=False, allow_null=True)
    port_operator_override = serializers.BooleanField(required=False, default=False)
    acknowledge_combined_red = serializers.BooleanField(required=False, default=False)
    override_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
    )

    def update(self, instance, validated_data):
        user = self.context.get("request").user if self.context.get("request") else None
        cancellation_evidence = validated_data.pop("cancellation_evidence", None)
        cancellation_reason = validated_data.pop("cancellation_reason", None)
        new_status = validated_data.pop("status", None)
        port_operator_override = validated_data.pop("port_operator_override", False)
        acknowledge_combined_red = validated_data.pop("acknowledge_combined_red", False)
        override_reason = validated_data.pop("override_reason", "")

        operational_keys = (
            "position",
            "eta",
            "etd",
            "eta_real",
            "etd_real",
            "planned_pax",
            "actual_pax",
            "actual_crew",
        )
        operational_fields = {
            key: validated_data[key] for key in operational_keys if key in validated_data
        }

        try:
            if new_status == BookingStatus.R:
                pre_r = {
                    k: v
                    for k, v in operational_fields.items()
                    if k not in ("actual_pax", "eta_real", "etd_real")
                }
                if pre_r:
                    instance = update_booking_operational(
                        instance,
                        user=user,
                        position_id=pre_r.get("position"),
                        eta=pre_r.get("eta"),
                        etd=pre_r.get("etd"),
                        planned_pax=pre_r.get("planned_pax"),
                        actual_crew=pre_r.get("actual_crew"),
                        port_operator_override=port_operator_override,
                        acknowledge_combined_red=acknowledge_combined_red,
                        override_reason=override_reason,
                    )
                instance = update_booking_status(
                    instance,
                    new_status,
                    user=user,
                    cancellation_reason=cancellation_reason,
                    cancellation_evidence=cancellation_evidence,
                    actual_pax=operational_fields.get("actual_pax"),
                    eta_real=operational_fields.get("eta_real"),
                    etd_real=operational_fields.get("etd_real"),
                    acknowledge_combined_red=acknowledge_combined_red,
                )
            else:
                if operational_fields:
                    instance = update_booking_operational(
                        instance,
                        user=user,
                        position_id=operational_fields.get("position"),
                        eta=operational_fields.get("eta"),
                        etd=operational_fields.get("etd"),
                        eta_real=operational_fields.get("eta_real"),
                        etd_real=operational_fields.get("etd_real"),
                        planned_pax=operational_fields.get("planned_pax"),
                        actual_pax=operational_fields.get("actual_pax"),
                        actual_crew=operational_fields.get("actual_crew"),
                        port_operator_override=port_operator_override,
                        acknowledge_combined_red=acknowledge_combined_red,
                        override_reason=override_reason,
                    )
                if new_status:
                    instance = update_booking_status(
                        instance,
                        new_status,
                        user=user,
                        cancellation_reason=cancellation_reason,
                        cancellation_evidence=cancellation_evidence,
                        acknowledge_combined_red=acknowledge_combined_red,
                    )
        except BookingValidationError as exc:
            field = "status" if new_status else "position"
            raise serializers.ValidationError({field: exc.errors}) from exc
        except BookingStatusError as exc:
            field = "status" if new_status else "non_field_errors"
            raise serializers.ValidationError({field: str(exc)}) from exc

        return instance


class BookingValidateSerializer(serializers.Serializer):
    port = serializers.IntegerField()
    vessel = serializers.IntegerField()
    call_dates = serializers.ListField(child=serializers.DateField(), allow_empty=False)
    position = serializers.IntegerField(required=False, allow_null=True)
    eta = serializers.TimeField(required=False, allow_null=True)
    etd = serializers.TimeField(required=False, allow_null=True)
    acknowledge_combined_red = serializers.BooleanField(required=False, default=False)

    def validate_call_dates(self, value):
        unique = sorted({d for d in value})
        if len(unique) != len(value):
            raise serializers.ValidationError("Las fechas deben ser únicas.")
        return unique

    def create(self, validated_data):
        from apps.bookings.services.booking.status import user_may_authorize_exceptions

        request = self.context.get("request")
        user = request.user if request else None
        ack = bool(validated_data.get("acknowledge_combined_red"))
        if ack and not user_may_authorize_exceptions(user):
            ack = False
        return validate_booking_params(
            port_id=validated_data["port"],
            vessel_id=validated_data["vessel"],
            call_dates=validated_data["call_dates"],
            position_id=validated_data.get("position"),
            eta=validated_data.get("eta"),
            etd=validated_data.get("etd"),
            acknowledge_combined_red=ack,
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
    eta = serializers.TimeField(required=False, allow_null=True)
    etd = serializers.TimeField(required=False, allow_null=True)
    planned_pax = serializers.IntegerField(required=False, allow_null=True, min_value=0)

    def validate_call_dates(self, value):
        if not value:
            raise serializers.ValidationError("Selecciona al menos una fecha.")
        unique = sorted({d for d in value})
        if len(unique) != len(value):
            raise serializers.ValidationError("Las fechas deben ser únicas.")
        return unique
