from rest_framework import serializers

from apps.catalogs.models import PositionLoaRecalcRule
from apps.catalogs.services.position_combination import position_is_combined
from apps.catalogs.utils.position_code import position_short_code


class PositionLoaRecalcRuleSerializer(serializers.ModelSerializer):
    position_a_code = serializers.CharField(source="position_a.code", read_only=True)
    position_a_label = serializers.SerializerMethodField()
    position_b_code = serializers.CharField(source="position_b.code", read_only=True)
    position_b_label = serializers.SerializerMethodField()

    class Meta:
        model = PositionLoaRecalcRule
        fields = [
            "id",
            "port",
            "position_a",
            "position_a_code",
            "position_a_label",
            "position_b",
            "position_b_code",
            "position_b_label",
            "max_loa_m",
            "separation_m",
            "yellow_from_m",
            "red_from_m",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_position_a_label(self, obj) -> str:
        return position_short_code(obj.port.code, obj.position_a.code)

    def get_position_b_label(self, obj) -> str:
        return position_short_code(obj.port.code, obj.position_b.code)

    def validate(self, attrs):
        port = attrs.get("port") or getattr(self.instance, "port", None)
        pos_a = attrs.get("position_a") or getattr(self.instance, "position_a", None)
        pos_b = attrs.get("position_b") or getattr(self.instance, "position_b", None)
        max_loa = attrs.get("max_loa_m")
        if max_loa is None and self.instance:
            max_loa = self.instance.max_loa_m
        yellow = attrs.get("yellow_from_m")
        if yellow is None and self.instance:
            yellow = self.instance.yellow_from_m
        red = attrs.get("red_from_m")
        if red is None and self.instance:
            red = self.instance.red_from_m
        sep = attrs.get("separation_m")
        if sep is None and self.instance:
            sep = self.instance.separation_m

        if pos_a and port and pos_a.port_id != port.id:
            raise serializers.ValidationError(
                {"position_a": "La posición debe pertenecer al puerto."}
            )
        if pos_b and port and pos_b.port_id != port.id:
            raise serializers.ValidationError(
                {"position_b": "La posición debe pertenecer al puerto."}
            )
        if pos_a and pos_b and pos_a.id == pos_b.id:
            raise serializers.ValidationError(
                {"position_b": "Las dos posiciones deben ser distintas."}
            )
        if pos_a and position_is_combined(pos_a):
            raise serializers.ValidationError(
                {"position_a": "Usa una posición física (no combinada)."}
            )
        if pos_b and position_is_combined(pos_b):
            raise serializers.ValidationError(
                {"position_b": "Usa una posición física (no combinada)."}
            )
        if sep is not None and sep < 0:
            raise serializers.ValidationError(
                {"separation_m": "La separación no puede ser negativa."}
            )
        if max_loa is not None and max_loa <= 0:
            raise serializers.ValidationError(
                {"max_loa_m": "La eslora máxima del muelle debe ser mayor que 0."}
            )
        if yellow is not None and red is not None and yellow >= red:
            raise serializers.ValidationError(
                {
                    "red_from_m": (
                        "El umbral rojo debe ser mayor que el umbral amarillo."
                    )
                }
            )
        if max_loa is not None and yellow is not None and yellow <= max_loa:
            raise serializers.ValidationError(
                {
                    "yellow_from_m": (
                        "El umbral amarillo debe ser mayor que la eslora máxima "
                        "(verde = suma menor a ese máximo)."
                    )
                }
            )
        return attrs
