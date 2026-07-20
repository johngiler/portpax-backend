from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.views.search import GlobalSearchView
from apps.core.views.nav_counts import NavCountsView

__all__ = ["health", "GlobalSearchView", "NavCountsView"]


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response(
        {
            "status": "ok",
            "service": "portpax-api",
            "env": getattr(settings, "PORTPAX_ENV", "unknown"),
        }
    )
