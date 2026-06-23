from django.contrib import admin

from apps.audit.models import BookingAuditEntry


@admin.register(BookingAuditEntry)
class BookingAuditEntryAdmin(admin.ModelAdmin):
    list_display = ("booking", "action", "summary", "user", "created_at")
    list_filter = ("action",)
    search_fields = ("booking__booking_code", "summary")
    readonly_fields = ("created_at",)
