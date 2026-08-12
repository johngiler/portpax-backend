from rest_framework import serializers

from apps.catalogs.models import PositionLoaRecalcRule
from apps.catalogs.services.position_combination import position_is_combined
from apps.catalogs.utils.position_code import position_short_code


class PositionLoaRecalcRuleSerializer(serializers.ModelSerializer):
    combined_position_code = serializers.CharField(
        source="combined_position.code",
        read_only=True,
    )
    combined_position_label = serializers.SerializerMethodField()
    combined_max_loa_m = serializers.SerializerMethodField()
    component_labels = serializers.SerializerMethodField()

    class Meta:
        model = PositionLoaRecalcRule
        fields = [
            "id",
            "port",
            "combined_position",
            "combined_position_code",
            "combined_position_label",
            "combined_max_loa_m",
            "component_labels",
            "min_separation_m",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_combined_position_label(self, obj) -> str:
        return position_short_code(obj.port.code, obj.combined_position.code)

    def get_combined_max_loa_m(self, obj) -> str | None:
        value = obj.combined_position.max_loa_m
        return str(value) if value is not None else None

    def get_component_labels(self, obj) -> list[str]:
        return [
            position_short_code(obj.port.code, link.source_position.code)
            for link in obj.combined_position.component_links.select_related(
                "source_position"
            ).order_by("sort_order")
        ]

    def validate(self, attrs):
        port = attrs.get("port") or getattr(self.instance, "port", None)
        combined = attrs.get("combined_position") or getattr(
            self.instance, "combined_position", None
        )
        if combined and port and combined.port_id != port.id:
            raise serializers.ValidationError(
                {"combined_position": "La posición combinada debe pertenecer al puerto."}
            )
        if combined and not position_is_combined(combined):
            raise serializers.ValidationError(
                {"combined_position": "Selecciona una posición combinada (p. ej. E1+E2)."}
            )
        if combined and combined.max_loa_m is None:
            raise serializers.ValidationError(
                {
                    "combined_position": (
                        "La posición combinada necesita eslora máxima "
                        "para recalcular el espacio sobrante."
                    )
                }
            )
        sep = attrs.get("min_separation_m")
        if sep is not None and sep < 0:
            raise serializers.ValidationError(
                {"min_separation_m": "La separación no puede ser negativa."}
            )
        return attrs
