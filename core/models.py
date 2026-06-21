"""
Shared data layer for the whole site.

`core` owns the raw synthetic data (Product, DailySale) and the single
AnalyticsResult join table that the orchestrator writes and every feature app
(analytics / dx_analytics / lifecycle / automation) reads its own slice of.
"""
from django.db import models


class Product(models.Model):
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    brand = models.CharField(max_length=80)

    cost_per_ml = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_size = models.CharField(max_length=8, default="10ml")

    current_inventory = models.IntegerField(default=0)
    lab_qty = models.IntegerField(default=0)    # decanted / perishable units
    wh_qty = models.IntegerField(default=0)     # sealed warehouse units
    avg_window_inventory = models.FloatField(default=0)

    liquid_opened_date = models.DateField(null=True, blank=True)
    is_new = models.BooleanField(default=False)
    created_at = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.sku} · {self.name}"


class DailySale(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="sales")
    date = models.DateField()
    units = models.IntegerField(default=0)

    class Meta:
        unique_together = ("product", "date")
        indexes = [models.Index(fields=["product", "date"])]


class AnalyticsResult(models.Model):
    """One row per product per engine run — the shared output store."""

    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="result")
    run_date = models.DateField()

    # base metrics (core)
    weighted_daily_sales = models.FloatField(default=0)
    velocity = models.FloatField(default=0)
    days_of_inventory = models.FloatField(default=0)
    roi = models.FloatField(default=0)
    inventory_value = models.FloatField(default=0)
    liquid_age_days = models.IntegerField(null=True, blank=True)

    # dx_analytics (v2)
    sell_through_rate = models.FloatField(default=0)
    portfolio_score = models.FloatField(default=0)
    portfolio_rank = models.IntegerField(default=0)
    category = models.CharField(max_length=40, default="Standard")
    category_reason = models.CharField(max_length=240, blank=True, default="")

    # lifecycle
    lifecycle_tier = models.CharField(max_length=16, default="CORE")
    liquidation_strategy = models.CharField(max_length=20, blank=True, default="")
    discount_pct = models.IntegerField(default=0)

    # analytics (v1)
    naive_sell_through = models.FloatField(default=0)
    sales_norm = models.FloatField(default=0)
    profit_norm = models.FloatField(default=0)
    roi_norm = models.FloatField(default=0)
    score_balanced = models.FloatField(default=0)
    is_pareto_optimal = models.BooleanField(default=False)
    v1_rank = models.IntegerField(default=0)
    v1_verdict = models.CharField(max_length=40, default="")

    # the cost-implied price tier (used for ROI; shown on the SKU page)
    expected_tier = models.CharField(max_length=4, blank=True, default="")

    class Meta:
        ordering = ["portfolio_rank"]

    def __str__(self):
        return f"{self.product.sku} → {self.category} ({self.lifecycle_tier})"
