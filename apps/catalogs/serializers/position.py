from rest_framework import serializers

from django.core.exceptions import ValidationError

from apps.catalogs.models import Position, PositionType
from apps.catalogs.services.position_combination import (
    clear_position_components,
    sync_position_components,
    validate_component_ids,
)


class PositionComponentRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()


class PositionSerializer(serializers.ModelSerializer):
    berth_code = serializers.CharField(
        source="berth.code",
        read_only=True,
        allow_null=True,
        default="",
    )
    port_name = serializers.CharField(source="port.name", read_only=True)
    port_code = serializers.CharField(source="port.code", read_only=True)
    is_combined = serializers.SerializerMethodField()
    component_positions = serializers.SerializerMethodField()
    component_position_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = Position
        fields = [
            "id",
            "port",
            "port_name",
            "port_code",
            "berth",
            "berth_code",
            "code",
            "position_type",
            "max_loa_m",
            "min_draft_m",
            "bollard_count",
            "fender_count",
            "effective_from",
            "effective_until",
            "notes",
            "latitude",
            "longitude",
            "sort_order",
            "is_active",
            "is_combined",
            "component_positions",
            "component_position_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "berth_code",
            "port_name",
            "port_code",
            "is_combined",
            "component_positions",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending_component_ids: list[int] | None | object = object()

    def get_is_combined(self, obj: Position) -> bool:
        return bool(self._component_links(obj))

    def get_component_positions(self, obj: Position) -> list[dict]:
        return [
            {"id": link.source_position_id, "code": link.source_position.code}
            for link in self._component_links(obj)
        ]

    def _component_links(self, obj: Position):
        if hasattr(obj, "_prefetched_component_links"):
            return obj._prefetched_component_links
        return list(obj.component_links.select_related("source_position").order_by("sort_order"))

    def validate(self, attrs):
        if "component_position_ids" in attrs:
            raw_ids = attrs.pop("component_position_ids")
            if raw_ids is None:
                self._pending_component_ids = None
            elif len(raw_ids) == 0:
                self._pending_component_ids = []
            elif len(raw_ids) == 2:
                port_id = attrs.get("port") or (self.instance.port_id if self.instance else None)
                if not port_id:
                    raise serializers.ValidationError({"port": "Requerido para posición combinada."})
                combined_id = self.instance.id if self.instance else None
                try:
                    sources = validate_component_ids(
                        port_id=port_id,
                        component_ids=raw_ids,
                        combined_position_id=combined_id,
                    )
                except ValidationError as exc:
                    message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
                    raise serializers.ValidationError({"component_position_ids": message}) from exc
                self._pending_component_ids = [source.id for source in sources]
                attrs.setdefault("position_type", PositionType.PIER)
            else:
                raise serializers.ValidationError(
                    {"component_position_ids": "Indica exactamente dos posiciones base o deja vacío."}
                )

        return attrs

    def create(self, validated_data):
        position = super().create(validated_data)
        self._apply_components(position)
        return position

    def update(self, instance, validated_data):
        position = super().update(instance, validated_data)
        if self._pending_component_ids is not object():
            self._apply_components(position)
        return position

    def _apply_components(self, position: Position) -> None:
        if self._pending_component_ids is object():
            return
        if self._pending_component_ids is None:
            return
        if self._pending_component_ids == []:
            clear_position_components(position)
            return

        sources = validate_component_ids(
            port_id=position.port_id,
            component_ids=self._pending_component_ids,
            combined_position_id=position.id,
        )
        sync_position_components(position, sources)
