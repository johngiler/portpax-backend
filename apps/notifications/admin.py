from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "recipient",
        "event",
        "message",
        "actor_display",
        "read_at",
        "created_at",
    )
    list_filter = ("event", "artifact", "target", "read_at")
    search_fields = ("message", "booking_code", "actor_display")
    readonly_fields = ("created_at",)
