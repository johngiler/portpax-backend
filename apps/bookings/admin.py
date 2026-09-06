from django.contrib import admin

from apps.audit.admin import ImmutableAuditAdminMixin
from apps.bookings.models import (
    Booking,
    BookingImportBatch,
    BookingRunBatch,
    BookingTag,
    LongTermAgreement,
)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        "booking_code",
        "port",
        "shipping_line",
        "vessel",
        "call_date",
        "status",
        "tag",
        "long_term_agreement",
        "created_at",
    ]
    list_filter = ["status", "port", "shipping_line", "tag"]
    search_fields = ["booking_code", "vessel__name", "port__code", "tag__name"]
    readonly_fields = ["booking_code", "created_at", "updated_at"]
    ordering = ["-call_date"]
    raw_id_fields = ["long_term_agreement", "tag"]


@admin.register(BookingTag)
class BookingTagAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name"]
    ordering = ["name"]


@admin.register(BookingImportBatch)
class BookingImportBatchAdmin(ImmutableAuditAdminMixin, admin.ModelAdmin):
    list_display = [
        "id",
        "label",
        "source",
        "tag",
        "created_count",
        "failed_count",
        "requested_count",
        "created_by",
        "created_at",
        "status",
    ]
    list_filter = ["source", "status"]
    search_fields = ["label", "tag__name"]
    ordering = ["-created_at"]
    raw_id_fields = ["tag"]


@admin.register(BookingRunBatch)
class BookingRunBatchAdmin(ImmutableAuditAdminMixin, admin.ModelAdmin):
    list_display = [
        "id",
        "kind",
        "label",
        "tag",
        "success_count",
        "failed_count",
        "created_by",
        "created_at",
    ]
    list_filter = ["kind"]
    search_fields = ["label", "tag__name"]
    ordering = ["-created_at"]
    raw_id_fields = ["tag"]


@admin.register(LongTermAgreement)
class LongTermAgreementAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "name",
        "port",
        "shipping_line",
        "all_vessels",
        "bookings_generated",
        "is_active",
    ]
    list_filter = ["is_active", "bookings_generated", "port", "shipping_line", "all_vessels"]
    search_fields = ["code", "name", "port__code", "shipping_line__code"]
    filter_horizontal = ["vessels", "positions"]
    readonly_fields = ["created_at", "updated_at", "bookings_generated"]
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
        "date_exceptions",
        "min_packs",
        "advance_months_min",
        "advance_months_max",
        "valid_from",
        "valid_until",
        "contract_file",
        "is_active",
        "bookings_generated",
        "notes",
        "created_at",
        "updated_at",
    ]
