from rest_framework import serializers

from apps.catalogs.models import Position, PositionNestingRule


class PositionNestingRuleSerializer(serializers.ModelSerializer):
    outer_position_code = serializers.CharField(
        source="outer_position.code",
        read_only=True,
    )
    inner_position_code = serializers.CharField(
        source="inner_position.code",
        read_only=True,
    )
    outer_position_label = serializers.SerializerMethodField()
    inner_position_label = serializers.SerializerMethodField()

    class Meta:
        model = PositionNestingRule
        fields = [
            "id",
            "port",
            "outer_position",
            "outer_position_code",
            "outer_position_label",
            "inner_position",
            "inner_position_code",
            "inner_position_label",
            "enforce_eta",
            "enforce_etd",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_outer_position_label(self, obj) -> str:
        code = obj.outer_position.code
        port_code = obj.port.code
        prefix = f"{port_code}-"
        return code.removeprefix(prefix) if code.startswith(prefix) else code

    def get_inner_position_label(self, obj) -> str:
        code = obj.inner_position.code
        port_code = obj.port.code
        prefix = f"{port_code}-"
        return code.removeprefix(prefix) if code.startswith(prefix) else code

    def validate(self, attrs):
        port = attrs.get("port") or getattr(self.instance, "port", None)
        outer = attrs.get("outer_position") or getattr(self.instance, "outer_position", None)
        inner = attrs.get("inner_position") or getattr(self.instance, "inner_position", None)

        if outer and port and outer.port_id != port.id:
            raise serializers.ValidationError(
                {"outer_position": "La posición entrada debe pertenecer al puerto."}
            )
        if inner and port and inner.port_id != port.id:
            raise serializers.ValidationError(
                {"inner_position": "La posición fondo debe pertenecer al puerto."}
            )
        if outer and inner and outer.id == inner.id:
            raise serializers.ValidationError(
                {"inner_position": "Entrada y fondo deben ser posiciones distintas."}
            )
        if outer and outer.component_links.exists():
            raise serializers.ValidationError(
                {"outer_position": "No uses una posición combinada como entrada."}
            )
        if inner and inner.component_links.exists():
            raise serializers.ValidationError(
                {"inner_position": "No uses una posición combinada como fondo."}
            )
        return attrs
