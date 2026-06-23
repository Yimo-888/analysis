from django.urls import path

from . import views

app_name = "analytics2"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("catalog/", views.catalog_list, name="catalog"),
    path("sku/<str:sku>/", views.sku_detail, name="sku_detail"),
]
