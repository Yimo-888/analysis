from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("catalog/", views.catalog_list, name="catalog"),
    path("sku/<str:sku>/", views.sku_detail, name="sku_detail"),
    path("pricing/", views.pricing, name="pricing"),
    path("mispricing/", views.mispricing, name="mispricing"),
    path("evolution/", views.evolution, name="evolution"),
]
