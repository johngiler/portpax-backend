from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views.media import serve_media

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("djoser.urls.jwt")),
    path("api/auth/", include("djoser.urls")),
    path("api/", include("apps.core.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/catalogs/", include("apps.catalogs.urls")),
    path("api/bookings/", include("apps.bookings.urls")),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    # PRODUCTION: nginx proxies /media/ here → default_storage (S3).
    # LOCAL (DEBUG): also covered below via static(); DEV nginx may alias disk.
    re_path(r"^media/(?P<path>.*)$", serve_media, name="serve_media"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
