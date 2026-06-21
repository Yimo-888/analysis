from django.contrib import admin

from .models import Listing, PostingJob


@admin.register(PostingJob)
class PostingJobAdmin(admin.ModelAdmin):
    list_display = ("name", "created_on", "status", "marketplace")
    list_filter = ("status", "marketplace")


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("variant_sku", "base_product", "variant_type", "size", "status", "posted_on")
    list_filter = ("status", "variant_type", "size")
    search_fields = ("variant_sku", "base_product__sku")
