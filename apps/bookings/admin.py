from django.contrib import admin

from apps.bookings.models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        "booking_code",
        "port",
        "shipping_line",
        "vessel",
        "call_date",
        "status",
        "created_at",
    ]
    list_filter = ["status", "port", "shipping_line"]
    search_fields = ["booking_code", "vessel__name", "port__code"]
    readonly_fields = ["booking_code", "created_at", "updated_at"]
    ordering = ["-call_date"]
