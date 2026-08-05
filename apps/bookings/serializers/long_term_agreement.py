from django.core.validators import FileExtensionValidator
from rest_framework import serializers

import json

from apps.bookings.models import LongTermAgreement
from apps.catalogs.models import Position, Vessel
from apps.catalogs.utils.position_code import position_short_code

CONTRACT_EXTENSIONS = ("pdf", "doc", "docx")


class LongTermAgreementSerializer(serializers.ModelSerializer):
    port_code = serializers.CharField(source="port.code", read_only=True)
    port_name = serializers.CharField(source="port.name", read_only=True)
    shipping_line_code = serializers.CharField(
        source="shipping_line.code",
        read_only=True,
    )
    shipping_line_name = serializers.CharField(
        source="shipping_line.name",
        read_only=True,
    )
    vessel_ids = serializers.PrimaryKeyRelatedField(
        source="vessels",
        many=True,
        queryset=Vessel.objects.all(),
        required=False,
    )
    position_ids = serializers.PrimaryKeyRelatedField(
        source="positions",
        many=True,
        queryset=Position.objects.all(),
        required=False,
    )
    vessel_names = serializers.SerializerMethodField()
    position_codes = serializers.SerializerMethodField()
    contract_file = serializers.FileField(
        required=False,
        allow_null=True,
        validators=[FileExtensionValidator(allowed_extensions=list(CONTRACT_EXTENSIONS))],
    )
    contract_file_url = serializers.SerializerMethodField()
    contract_file_name = serializers.SerializerMethodField()

    class Meta:
        model = LongTermAgreement
        fields = [
            "id",
            "code",
            "name",
            "port",
            "port_code",
            "port_name",
            "shipping_line",
            "shipping_line_code",
            "shipping_line_name",
            "all_vessels",
            "vessel_ids",
            "vessel_names",
            "position_ids",
            "position_codes",
            "weekdays",
            "interval_days",
            "cadence_anchor",
            "min_packs",
            "advance_months_min",
            "advance_months_max",
            "valid_from",
            "valid_until",
            "is_active",
            "notes",
            "contract_file",
            "contract_file_url",
            "contract_file_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "contract_file_url", "contract_file_name"]
        extra_kwargs = {
            "contract_file": {"write_only": True},
        }

    def get_vessel_names(self, obj) -> list[str]:
        return list(obj.vessels.order_by("name").values_list("name", flat=True))

    def get_position_codes(self, obj) -> list[str]:
        return [
            position_short_code(obj.port.code, p.code)
            for p in obj.positions.all()
        ]

    def _file_url(self, field) -> str | None:
        if not field:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(field.url)
        return field.url

    def get_contract_file_url(self, obj) -> str | None:
        return self._file_url(obj.contract_file)

    def get_contract_file_name(self, obj) -> str | None:
        if not obj.contract_file:
            return None
        name = obj.contract_file.name
        return name.rsplit("/", 1)[-1] if name else None

    def to_internal_value(self, data):
        # Multipart may send list fields as repeated keys or JSON strings.
        mutable = data
        if hasattr(data, "copy"):
            mutable = data.copy()
        elif isinstance(data, dict):
            mutable = {**data}

        for key in ("weekdays", "vessel_ids", "position_ids"):
            if key not in mutable:
                continue
            raw = mutable.get(key)
            if isinstance(raw, str):
                raw = raw.strip()
                if raw.startswith("["):
                    try:
                        mutable[key] = json.loads(raw)
                    except json.JSONDecodeError:
                        pass
                elif raw == "":
                    mutable[key] = []
        return super().to_internal_value(mutable)

    def validate_weekdays(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("Debe ser una lista de enteros 0–6.")
        normalized = []
        for day in value:
            try:
                day_i = int(day)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    "Cada día debe ser un entero 0 (lun) a 6 (dom)."
                ) from exc
            if day_i < 0 or day_i > 6:
                raise serializers.ValidationError(
                    "Cada día debe ser un entero 0 (lun) a 6 (dom)."
                )
            normalized.append(day_i)
        return normalized

    def validate(self, attrs):
        port = attrs.get("port") or getattr(self.instance, "port", None)
        shipping_line = attrs.get("shipping_line") or getattr(
            self.instance, "shipping_line", None
        )
        all_vessels = attrs.get(
            "all_vessels",
            getattr(self.instance, "all_vessels", True),
        )
        vessels = attrs.get("vessels")
        if vessels is None and self.instance:
            vessels = list(self.instance.vessels.all())
        vessels = vessels or []
        positions = attrs.get("positions")
        if positions is None and self.instance:
            positions = list(self.instance.positions.all())
        positions = positions or []

        advance_min = attrs.get(
            "advance_months_min",
            getattr(self.instance, "advance_months_min", 18),
        )
        advance_max = attrs.get(
            "advance_months_max",
            getattr(self.instance, "advance_months_max", 32),
        )
        if advance_min > advance_max:
            raise serializers.ValidationError(
                {"advance_months_min": "Debe ser menor o igual al máximo."}
            )

        if not all_vessels and not vessels:
            raise serializers.ValidationError(
                {"vessel_ids": "Selecciona barcos o marca «todos los barcos»."}
            )
        for vessel in vessels:
            if shipping_line and vessel.shipping_line_id != shipping_line.id:
                raise serializers.ValidationError(
                    {"vessel_ids": f"El barco {vessel.name} no pertenece a la naviera."}
                )
        for position in positions:
            if port and position.port_id != port.id:
                raise serializers.ValidationError(
                    {"position_ids": f"La posición {position.code} no pertenece al puerto."}
                )

        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_until = attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if valid_from and valid_until and valid_from > valid_until:
            raise serializers.ValidationError(
                {"valid_until": "Debe ser posterior o igual a la fecha de inicio."}
            )

        interval_days = attrs.get(
            "interval_days",
            getattr(self.instance, "interval_days", None),
        )
        cadence_anchor = attrs.get(
            "cadence_anchor",
            getattr(self.instance, "cadence_anchor", None),
        )
        if (interval_days is None) ^ (cadence_anchor is None):
            raise serializers.ValidationError(
                {
                    "interval_days": "Cadencia y fecha ancla van juntas.",
                    "cadence_anchor": "Cadencia y fecha ancla van juntas.",
                }
            )
        if interval_days is not None and interval_days < 1:
            raise serializers.ValidationError(
                {"interval_days": "Debe ser al menos 1."}
            )
        return attrs

    def create(self, validated_data):
        vessels = validated_data.pop("vessels", [])
        positions = validated_data.pop("positions", [])
        contract_file = validated_data.pop("contract_file", None)
        if contract_file in (None, ""):
            validated_data.pop("contract_file", None)
            agreement = LongTermAgreement.objects.create(**validated_data)
        else:
            agreement = LongTermAgreement.objects.create(
                **validated_data,
                contract_file=contract_file,
            )
        if vessels:
            agreement.vessels.set(vessels)
        if positions:
            agreement.positions.set(positions)
        return agreement

    def update(self, instance, validated_data):
        vessels = validated_data.pop("vessels", None)
        positions = validated_data.pop("positions", None)
        contract_file = validated_data.pop("contract_file", serializers.empty)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if contract_file is not serializers.empty:
            if contract_file in (None, ""):
                if instance.contract_file:
                    instance.contract_file.delete(save=False)
                instance.contract_file = None
            else:
                instance.contract_file = contract_file
        instance.save()
        if vessels is not None:
            instance.vessels.set(vessels)
        if positions is not None:
            instance.positions.set(positions)
        return instance
