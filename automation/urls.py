from django.urls import path

from . import views

app_name = "automation"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
]
