from django.contrib import admin
from django.contrib.auth import get_user_model

from apps.accounts.models import UserPortAccess, UserProfile

User = get_user_model()


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "created_at", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(is_superuser=False).order_by(
                "username"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(UserPortAccess)
class UserPortAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "port", "created_at")
    list_filter = ("port",)
    search_fields = ("user__username", "port__name", "port__code")
    autocomplete_fields = ("user", "port")
    readonly_fields = ("created_at",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(is_superuser=False).order_by(
                "username"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
