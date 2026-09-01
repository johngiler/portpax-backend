from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "event",
            "artifact",
            "target",
            "message",
            "actor_display",
            "booking_id",
            "booking_code",
            "port_id",
            "batch_id",
            "affected_count",
            "history_type_filter",
            "read_at",
            "is_read",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_read(self, obj) -> bool:
        return obj.read_at is not None
