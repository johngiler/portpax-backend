from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import UserPortAccess, UserProfile, UserRole
from apps.catalogs.models import Port

User = get_user_model()


class ManagedUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    port_ids = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "role",
            "port_ids",
            "avatar",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields

    def get_role(self, obj) -> str | None:
        try:
            return obj.profile.role
        except UserProfile.DoesNotExist:
            return None

    def get_port_ids(self, obj) -> list[int]:
        return sorted(obj.port_access.values_list("port_id", flat=True))

    def get_avatar(self, obj) -> str | None:
        from apps.accounts.serializers.current_user import profile_avatar_url

        return profile_avatar_url(obj, self.context.get("request"))


class ManagedUserWriteSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True, required=False)
    role = serializers.ChoiceField(choices=UserRole.choices)
    port_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_username(self, value: str) -> str:
        qs = User.objects.filter(username=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un usuario con ese nombre.")
        return value

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate_port_ids(self, value: list[int]) -> list[int]:
        if not value:
            return []
        existing = set(Port.objects.filter(id__in=value).values_list("id", flat=True))
        missing = sorted(set(value) - existing)
        if missing:
            raise serializers.ValidationError("Uno o más puertos no existen.")
        return sorted(existing)

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "La contraseña es obligatoria."})
        if attrs.get("role") == UserRole.ADMIN:
            attrs["port_ids"] = []
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        role = validated_data.pop("role")
        port_ids = validated_data.pop("port_ids", [])
        user = User.objects.create_user(
            password=password,
            is_staff=False,
            is_superuser=False,
            **validated_data,
        )
        UserProfile.objects.create(user=user, role=role)
        self._sync_ports(user, role, port_ids)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        role = validated_data.pop("role")
        port_ids = validated_data.pop("port_ids", [])
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.is_superuser = False
        if password:
            instance.set_password(password)
        instance.save()
        profile, _ = UserProfile.objects.get_or_create(
            user=instance,
            defaults={"role": role},
        )
        if profile.role != role:
            profile.role = role
            profile.save(update_fields=["role", "updated_at"])
        self._sync_ports(instance, role, port_ids)
        return instance

    def _sync_ports(self, user, role: str, port_ids: list[int]) -> None:
        UserPortAccess.objects.filter(user=user).delete()
        if role == UserRole.ADMIN:
            return
        UserPortAccess.objects.bulk_create(
            [UserPortAccess(user=user, port_id=port_id) for port_id in port_ids]
        )


class MeProfileSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    port_ids = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "port_ids",
            "avatar",
        ]
        read_only_fields = ["id", "username", "role", "port_ids", "avatar"]

    def get_role(self, obj) -> str | None:
        try:
            return obj.profile.role
        except UserProfile.DoesNotExist:
            return None

    def get_port_ids(self, obj) -> list[int] | None:
        from apps.accounts.permissions import user_port_ids

        allowed = user_port_ids(obj)
        if allowed is None:
            return None
        return sorted(allowed)

    def get_avatar(self, obj) -> str | None:
        from apps.accounts.serializers.current_user import profile_avatar_url

        return profile_avatar_url(obj, self.context.get("request"))

    def update(self, instance, validated_data):
        from apps.core.utils.image_webp import (
            ImageConversionError,
            convert_uploaded_image_to_webp,
        )

        instance = super().update(instance, validated_data)
        request = self.context.get("request")
        if request is None:
            return instance

        avatar_in_files = "avatar" in getattr(request, "FILES", {})
        avatar_in_data = hasattr(request, "data") and "avatar" in request.data
        if not avatar_in_files and not avatar_in_data:
            return instance

        profile, _ = UserProfile.objects.get_or_create(
            user=instance,
            defaults={"role": UserRole.BOOKING_OPERATOR},
        )
        uploaded = request.FILES.get("avatar") if avatar_in_files else None
        if uploaded:
            try:
                converted = convert_uploaded_image_to_webp(uploaded)
            except ImageConversionError as exc:
                raise serializers.ValidationError({"avatar": [exc.message]}) from exc
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = converted
        else:
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = None
        profile.save(update_fields=["avatar", "updated_at"])
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return value

    def validate_new_password(self, value: str) -> str:
        validate_password(value, user=self.context["request"].user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
