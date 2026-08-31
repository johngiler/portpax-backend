from rest_framework import serializers

from apps.audit.models import LtaAuditEntry, PortAuditEntry, ShippingLineAuditEntry
from apps.audit.utils.friendly_changes import (
    enrich_lta_audit_changes,
    enrich_port_audit_changes,
    enrich_shipping_line_audit_changes,
)


def _actor_username(entry) -> str | None:
    if not entry.actor_id:
        return None
    return entry.actor.get_username()


class LtaAuditEntrySerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = LtaAuditEntry
        fields = [
            "id",
            "action",
            "summary",
            "changes",
            "user_display",
            "created_at",
        ]

    def get_user_display(self, obj) -> str | None:
        return _actor_username(obj)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        raw = instance.changes if isinstance(instance.changes, dict) else {}
        data["changes"] = enrich_lta_audit_changes(raw) or {}
        return data


class PortAuditEntrySerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = PortAuditEntry
        fields = [
            "id",
            "action",
            "summary",
            "changes",
            "user_display",
            "created_at",
        ]

    def get_user_display(self, obj) -> str | None:
        return _actor_username(obj)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        raw = instance.changes if isinstance(instance.changes, dict) else {}
        data["changes"] = enrich_port_audit_changes(raw) or {}
        return data


class ShippingLineAuditEntrySerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = ShippingLineAuditEntry
        fields = [
            "id",
            "action",
            "summary",
            "changes",
            "user_display",
            "created_at",
        ]

    def get_user_display(self, obj) -> str | None:
        return _actor_username(obj)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        raw = instance.changes if isinstance(instance.changes, dict) else {}
        data["changes"] = enrich_shipping_line_audit_changes(raw) or {}
        return data
