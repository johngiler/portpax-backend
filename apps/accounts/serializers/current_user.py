from djoser.serializers import UserSerializer as DjoserUserSerializer
from rest_framework import serializers

from apps.accounts.models import UserProfile
from apps.accounts.permissions import user_port_ids, user_role


def profile_avatar_url(user, request) -> str | None:
    try:
        avatar = user.profile.avatar
    except UserProfile.DoesNotExist:
        return None
    if not avatar:
        return None
    url = avatar.url
    if request is not None:
        try:
            return request.build_absolute_uri(url)
        except Exception:
            return url
    return url


class CurrentUserSerializer(DjoserUserSerializer):
    """Djoser current-user payload with MVP role, ports, and avatar."""

    role = serializers.SerializerMethodField()
    port_ids = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    class Meta(DjoserUserSerializer.Meta):
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "port_ids",
            "avatar",
        )
        read_only_fields = (
            "id",
            "username",
            "role",
            "port_ids",
            "avatar",
        )

    def get_role(self, obj) -> str:
        return user_role(obj)

    def get_port_ids(self, obj) -> list[int] | None:
        """Null means all ports (admin); otherwise explicit port id list."""
        allowed = user_port_ids(obj)
        if allowed is None:
            return None
        return sorted(allowed)

    def get_avatar(self, obj) -> str | None:
        return profile_avatar_url(obj, self.context.get("request"))
