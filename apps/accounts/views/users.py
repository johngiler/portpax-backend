from django.contrib.auth import get_user_model
from rest_framework import filters, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole, IsFrontendAppUser
from apps.accounts.serializers.users import (
    ChangePasswordSerializer,
    ManagedUserSerializer,
    ManagedUserWriteSerializer,
    MeProfileSerializer,
)

User = get_user_model()


class ManagedUserViewSet(viewsets.ModelViewSet):
    """CRUD for frontend app users (admin MVP role only). Never manages superusers."""

    permission_classes = [IsAuthenticated, IsFrontendAppUser, IsAdminRole]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends = [filters.SearchFilter]
    search_fields = ["username", "email", "first_name", "last_name"]

    def get_queryset(self):
        return (
            User.objects.filter(is_superuser=False)
            .select_related("profile")
            .prefetch_related("port_access")
            .order_by("username")
        )

    def get_serializer_class(self):
        if self.action in ("create", "partial_update", "update"):
            return ManagedUserWriteSerializer
        return ManagedUserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            ManagedUserSerializer(user, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            ManagedUserSerializer(user, context={"request": request}).data
        )

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response(
                {"detail": "No puedes eliminar tu propio usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeProfileView(APIView):
    permission_classes = [IsAuthenticated, IsFrontendAppUser]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        return Response(MeProfileSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        serializer = MeProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        user = User.objects.select_related("profile").get(pk=request.user.pk)
        return Response(MeProfileSerializer(user, context={"request": request}).data)


class MeChangePasswordView(APIView):
    permission_classes = [IsAuthenticated, IsFrontendAppUser]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Contraseña actualizada."})
