from django.contrib import admin

from apps.audit.models import BookingAuditEntry, LtaAuditEntry, UserAuditEntry
from apps.audit.services.deletion import allow_audit_deletion


class ImmutableAuditAdminMixin:
    """Read-mostly audit admin: no add; delete only for Django superusers."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        names = [f.name for f in self.model._meta.fields]
        return tuple(dict.fromkeys([*getattr(self, "readonly_fields", ()), *names]))

    def delete_model(self, request, obj):
        with allow_audit_deletion():
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with allow_audit_deletion():
            super().delete_queryset(request, queryset)


@admin.register(BookingAuditEntry)
class BookingAuditEntryAdmin(ImmutableAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "booking_code",
        "booking",
        "action",
        "summary",
        "user",
        "created_at",
    )
    list_filter = ("action",)
    search_fields = ("booking_code", "booking__booking_code", "summary")


@admin.register(UserAuditEntry)
class UserAuditEntryAdmin(ImmutableAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "subject_username",
        "action",
        "summary",
        "actor",
        "subject_role",
        "created_at",
    )
    list_filter = ("action", "subject_role", "subject_is_active")
    search_fields = ("subject_username", "subject_display", "summary")


@admin.register(LtaAuditEntry)
class LtaAuditEntryAdmin(ImmutableAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        "agreement_code",
        "agreement_name",
        "action",
        "summary",
        "actor",
        "port_code",
        "created_at",
    )
    list_filter = ("action",)
    search_fields = ("agreement_code", "agreement_name", "summary", "port_code")
