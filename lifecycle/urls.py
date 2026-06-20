from django.urls import path

from . import views

app_name = "lifecycle"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("clearance/", views.clearance, name="clearance"),
]
