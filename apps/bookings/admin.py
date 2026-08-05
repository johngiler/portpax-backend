from django.contrib import admin

from apps.audit.admin import ImmutableAuditAdminMixin
from apps.bookings.models import Booking, BookingImportBatch, LongTermAgreement


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        "booking_code",
        "port",
        "shipping_line",
        "vessel",
        "call_date",
        "status",
        "long_term_agreement",
        "created_at",
    ]
    list_filter = ["status", "port", "shipping_line"]
    search_fields = ["booking_code", "vessel__name", "port__code"]
    readonly_fields = ["booking_code", "created_at", "updated_at"]
    ordering = ["-call_date"]
    raw_id_fields = ["long_term_agreement"]


@admin.register(BookingImportBatch)
class BookingImportBatchAdmin(ImmutableAuditAdminMixin, admin.ModelAdmin):
    list_display = [
        "id",
        "label",
        "source",
        "created_count",
        "failed_count",
        "requested_count",
        "created_by",
        "created_at",
        "status",
    ]
    list_filter = ["source", "status"]
    search_fields = ["label"]
    ordering = ["-created_at"]


@admin.register(LongTermAgreement)
class LongTermAgreementAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "name",
        "port",
        "shipping_line",
        "all_vessels",
        "advance_months_min",
        "advance_months_max",
        "is_active",
    ]
    list_filter = ["is_active", "port", "shipping_line", "all_vessels"]
    search_fields = ["code", "name", "port__code", "shipping_line__code"]
    filter_horizontal = ["vessels", "positions"]
    readonly_fields = ["created_at", "updated_at"]
    fields = [
        "code",
        "name",
        "port",
        "shipping_line",
        "all_vessels",
        "vessels",
        "positions",
        "weekdays",
        "interval_days",
        "cadence_anchor",
        "min_packs",
        "advance_months_min",
        "advance_months_max",
        "valid_from",
        "valid_until",
        "contract_file",
        "is_active",
        "notes",
        "created_at",
        "updated_at",
    ]
