from django.db import IntegrityError
from rest_framework import serializers

from apps.catalogs.models import Berth


class BerthSerializer(serializers.ModelSerializer):
    class Meta:
        model = Berth
        fields = [
            "id",
            "port",
            "code",
            "name",
            "length_m",
            "width_m",
            "walkway_length_m",
            "walkway_width_m",
            "min_draft_m",
            "notes",
            "latitude",
            "longitude",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        validators = []
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        port = attrs.get("port")
        code = attrs.get("code")
        port_id = port.pk if hasattr(port, "pk") else port
        if port_id is None and self.instance:
            port_id = self.instance.port_id
        if code is None and self.instance:
            code = self.instance.code

        if port_id and code:
            duplicate_qs = Berth.objects.filter(port_id=port_id, code=code)
            if self.instance:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
            if duplicate_qs.exists():
                raise serializers.ValidationError(
                    {"code": "Ya existe un muelle con ese código en el puerto seleccionado."}
                )

        return attrs

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except IntegrityError as exc:
            raise self._integrity_error(exc) from exc

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except IntegrityError as exc:
            raise self._integrity_error(exc) from exc

    def _integrity_error(self, exc: IntegrityError) -> serializers.ValidationError:
        message = str(exc)
        if "uniq_berth_code_per_port" in message or "catalogs_berth.port_id" in message:
            return serializers.ValidationError(
                {"code": "Ya existe un muelle con ese código en el puerto seleccionado."}
            )
        return serializers.ValidationError(
            {
                "non_field_errors": [
                    "No se pudo guardar el muelle por un conflicto de datos."
                ]
            }
        )
