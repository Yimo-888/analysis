from django.urls import path

from . import views

app_name = "automation"

urlpatterns = [
    path("", views.pricing, name="pricing"),
    path("mispricing/", views.mispricing, name="mispricing"),
]
