from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.services.booking import mark_notification_read


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = self.get_queryset().filter(read_at__isnull=True).count()
        return Response({"count": count})

    @action(detail=True, methods=["post"], url_path="read")
    def read(self, request, pk=None):
        notification = self.get_object()
        mark_notification_read(notification)
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        now = timezone.now()
        updated = (
            self.get_queryset()
            .filter(read_at__isnull=True)
            .update(read_at=now)
        )
        return Response({"updated": updated})
