from rest_framework import serializers

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.catalogs.models import Port, PortBollard, PortFender, Position, PositionType
from apps.catalogs.services.position_combination import (
    clear_position_components,
    sync_position_components,
    validate_component_ids,
)
from apps.catalogs.utils.position_code import build_position_code, position_short_code

_PENDING_COMPONENTS_UNSET = object()


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
    short_code = serializers.SerializerMethodField()
    is_combined = serializers.SerializerMethodField()
    component_positions = serializers.SerializerMethodField()
    component_position_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_null=True,
        write_only=True,
    )
    port_bollard_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=PortBollard.objects.all(),
        source="port_bollards",
        required=False,
    )
    port_fender_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=PortFender.objects.all(),
        source="port_fenders",
        required=False,
    )

    class Meta:
        model = Position
        fields = [
            "id",
            "port",
            "port_name",
            "port_code",
            "short_code",
            "berth",
            "berth_code",
            "code",
            "position_type",
            "max_loa_m",
            "min_draft_m",
            "port_bollard_ids",
            "port_fender_ids",
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
        validators = []
        read_only_fields = [
            "id",
            "berth_code",
            "port_name",
            "port_code",
            "short_code",
            "is_combined",
            "component_positions",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending_component_ids: list[int] | None | object = _PENDING_COMPONENTS_UNSET

    def get_short_code(self, obj: Position) -> str:
        return position_short_code(obj.port.code, obj.code)

    def get_is_combined(self, obj: Position) -> bool:
        return bool(self._component_links(obj))

    def get_component_positions(self, obj: Position) -> list[dict]:
        return [
            {
                "id": link.source_position_id,
                "code": position_short_code(obj.port.code, link.source_position.code),
            }
            for link in self._component_links(obj)
        ]

    def _component_links(self, obj: Position):
        if hasattr(obj, "_prefetched_component_links"):
            return obj._prefetched_component_links
        return list(obj.component_links.select_related("source_position").order_by("sort_order"))

    def _resolve_port(self, attrs) -> tuple[int | None, str | None]:
        port = attrs.get("port")
        if port is None and self.instance:
            return self.instance.port_id, self.instance.port.code
        if port is None:
            return None, None
        if isinstance(port, Port):
            return port.pk, port.code
        return int(port), Port.objects.values_list("code", flat=True).get(pk=int(port))

    def validate(self, attrs):
        if "component_position_ids" in attrs:
            raw_ids = attrs.pop("component_position_ids")
            if raw_ids is None:
                self._pending_component_ids = None
            elif len(raw_ids) == 0:
                self._pending_component_ids = []
            elif len(raw_ids) == 2:
                port_id, _port_code = self._resolve_port(attrs)
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

        _port_id, port_code = self._resolve_port(attrs)
        if port_code and "code" in attrs:
            attrs["code"] = build_position_code(port_code, attrs["code"])

        if _port_id and "code" in attrs:
            duplicate_qs = Position.objects.filter(port_id=_port_id, code=attrs["code"])
            if self.instance:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
            if duplicate_qs.exists():
                short = position_short_code(port_code or "", attrs["code"])
                raise serializers.ValidationError(
                    {"code": f"Ya existe una posición «{short}» en este puerto."}
                )

        self._apply_inventory_links(attrs, _port_id)

        return attrs

    def _apply_inventory_links(self, attrs, port_id: int | None) -> None:
        if not port_id:
            return

        if "port_bollards" in attrs:
            bollards = attrs.get("port_bollards") or []
            for bollard in bollards:
                if bollard.port_id != port_id:
                    raise serializers.ValidationError(
                        {"port_bollard_ids": "Todas las bitas deben pertenecer al mismo puerto."}
                    )
            attrs["bollard_count"] = sum(b.quantity for b in bollards) if bollards else None

        if "port_fenders" in attrs:
            fenders = attrs.get("port_fenders") or []
            for fender in fenders:
                if fender.port_id != port_id:
                    raise serializers.ValidationError(
                        {"port_fender_ids": "Todas las defensas deben pertenecer al mismo puerto."}
                    )
            attrs["fender_count"] = sum(f.quantity for f in fenders) if fenders else None

    def create(self, validated_data):
        try:
            position = super().create(validated_data)
        except IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        self._apply_components(position)
        return position

    def update(self, instance, validated_data):
        try:
            position = super().update(instance, validated_data)
        except IntegrityError as exc:
            raise self._integrity_error(exc) from exc
        if self._pending_component_ids is not _PENDING_COMPONENTS_UNSET:
            self._apply_components(position)
        return position

    def _integrity_error(self, exc: IntegrityError) -> serializers.ValidationError:
        message = str(exc)
        if "uniq_position_code_per_port" in message or "catalogs_position.port_id" in message:
            return serializers.ValidationError(
                {"code": "Ya existe una posición con ese nombre en este puerto."}
            )
        return serializers.ValidationError(
            {
                "non_field_errors": [
                    "No se pudo guardar la posición por un conflicto de datos."
                ]
            }
        )

    def _apply_components(self, position: Position) -> None:
        if self._pending_component_ids is _PENDING_COMPONENTS_UNSET:
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
