"""
automation — automated listing posting.

The real workflow this models: a base product (one fragrance) is fanned out into
many marketplace listings — one per (bottle type × size) variant — and those
listings are generated and posted to the marketplace in bulk *batch jobs*, with
per-item status tracking (posted / pending / failed).

Two models capture that:
    PostingJob  — one batch run
    Listing     — one generated variant listing produced by a job
"""
from django.db import models

from core.models import Product


class PostingJob(models.Model):
    QUEUED, PROCESSING, COMPLETED, FAILED = "QUEUED", "PROCESSING", "COMPLETED", "FAILED"
    STATUS_CHOICES = [(QUEUED, "Queued"), (PROCESSING, "Processing"),
                      (COMPLETED, "Completed"), (FAILED, "Failed")]

    name = models.CharField(max_length=120)
    created_on = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=COMPLETED)
    marketplace = models.CharField(max_length=40, default="Marketplace")

    class Meta:
        ordering = ["-created_on", "-id"]

    def __str__(self):
        return f"{self.name} ({self.status})"

    # convenience counters computed from the related listings
    @property
    def total(self):
        return self.listings.count()

    @property
    def posted(self):
        return self.listings.filter(status=Listing.POSTED).count()

    @property
    def failed(self):
        return self.listings.filter(status=Listing.FAILED).count()

    @property
    def pending(self):
        return self.listings.filter(status=Listing.PENDING).count()

    @property
    def progress_pct(self):
        t = self.total
        return round(100 * self.posted / t) if t else 0


class Listing(models.Model):
    POSTED, PENDING, FAILED = "POSTED", "PENDING", "FAILED"
    STATUS_CHOICES = [(POSTED, "Posted"), (PENDING, "Pending"), (FAILED, "Failed")]

    job = models.ForeignKey(PostingJob, on_delete=models.CASCADE, related_name="listings")
    base_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="listings")
    variant_sku = models.CharField(max_length=48, unique=True)
    bottle_type = models.CharField(max_length=16)   # Vial / Atomizer
    size = models.CharField(max_length=8)
    title = models.CharField(max_length=160)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=POSTED)
    failed_reason = models.CharField(max_length=120, blank=True, default="")
    posted_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["job_id", "variant_sku"]

    def __str__(self):
        return self.variant_sku
