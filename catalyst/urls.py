from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("analytics/", include("analytics.urls")),
    path("analytics-v2/", include("analytics2.urls")),
    path("automation/", include("automation.urls")),
    path("lifecycle/", include("lifecycle.urls")),
]
