from django.utils import timezone
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)

from apps.accounts.services.frontend_access import (
    frontend_access_denial_message,
    user_may_use_frontend,
)
from apps.accounts.services.user_audit import snapshot_user
from apps.audit.services.record import record_user_audit


def _ensure_frontend_user(user) -> None:
    if user_may_use_frontend(user):
        return
    raise AuthenticationFailed(frontend_access_denial_message(user))


class FrontendTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issue JWT only for non-superusers that have an assigned MVP role."""

    def validate(self, attrs):
        data = super().validate(attrs)
        _ensure_frontend_user(self.user)
        self.user.last_login = timezone.now()
        self.user.save(update_fields=["last_login"])
        snap = snapshot_user(self.user)
        request = self.context.get("request")
        record_user_audit(
            action="login",
            summary="Inició sesión",
            subject=self.user,
            subject_username=snap["username"],
            subject_display=snap["display"],
            subject_role=snap["role"],
            subject_is_active=snap["is_active"],
            actor=self.user,
            request=request,
        )
        return data


class FrontendTokenRefreshSerializer(TokenRefreshSerializer):
    """Reject refresh for superusers or users without a role profile."""

    def validate(self, attrs):
        data = super().validate(attrs)
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken(attrs["refresh"])
        user_id = refresh.payload.get("user_id")
        user = get_user_model().objects.filter(pk=user_id).first()
        _ensure_frontend_user(user)
        return data
