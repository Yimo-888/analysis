from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("product/<str:sku>/", views.product_json, name="product_json"),
]
