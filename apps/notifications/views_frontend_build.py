"""Deploy-only endpoint to publish a new frontend build id."""

from __future__ import annotations

import hmac

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.services.frontend_build import publish_frontend_build_id

TOKEN_HEADER = "HTTP_X_PORTPAX_BUILD_TOKEN"


class FrontendBuildPublishView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        expected = (getattr(settings, "FRONTEND_BUILD_PUBLISH_TOKEN", "") or "").strip()
        if not expected:
            return Response(
                {"detail": "Frontend build publish is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provided = (request.META.get(TOKEN_HEADER) or "").strip()
        if not provided or not hmac.compare_digest(provided, expected):
            return Response(
                {"detail": "Invalid build publish token."},
                status=status.HTTP_403_FORBIDDEN,
            )

        build_id = request.data.get("build_id")
        if not isinstance(build_id, str) or not build_id.strip():
            return Response(
                {"detail": "build_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = publish_frontend_build_id(build_id.strip())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)
