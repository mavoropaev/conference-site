from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("conferences.urls")),
    path("", include("submissions.urls")),
    path("", include("reviews.urls")),
    path("", include("organizer.urls")),
    path("accounts/", include("accounts.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    # Загруженные файлы раздаются только в режиме разработки; в боевом режиме их отдаёт nginx.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
