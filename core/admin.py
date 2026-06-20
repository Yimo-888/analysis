from django.contrib import admin

from .models import AnalyticsResult, DailySale, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "brand", "cost_per_ml", "current_inventory",
                    "lab_qty", "wh_qty", "is_new")
    search_fields = ("sku", "name", "brand")
    list_filter = ("brand", "is_new", "max_size")


@admin.register(AnalyticsResult)
class AnalyticsResultAdmin(admin.ModelAdmin):
    list_display = ("product", "portfolio_rank", "category", "lifecycle_tier", "discount_pct")
    list_filter = ("category", "lifecycle_tier")
    search_fields = ("product__sku", "product__name")


admin.site.register(DailySale)
