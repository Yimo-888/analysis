"""
analytics (v1) — the classical inventory-theory metrics, persisted per product.

This is the original "textbook" design: weighted demand, safety stock, reorder
point, EOQ, inventory turnover, Pareto-optimal status. The dashboard reads these
directly; the per-window sales trend for the detail modal is computed on the fly.
"""
from django.db import models

from core.models import Product


class ProductStats(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="v1stats")
    run_date = models.DateField()

    # table columns
    stock = models.IntegerField(default=0)
    daily_sales = models.FloatField(default=0)
    days_supply = models.IntegerField(default=0)
    total_profit = models.FloatField(default=0)
    roi_pct = models.FloatField(default=0)
    score = models.FloatField(default=0)
    is_pareto = models.BooleanField(default=False)
    status = models.CharField(max_length=12, default="Optimize")

    # detail: performance
    profit_per_day = models.FloatField(default=0)
    sell_through_pct = models.FloatField(default=0)

    # detail: inventory management
    reorder_point = models.IntegerField(default=0)
    eoq = models.IntegerField(default=0)
    safety_stock = models.IntegerField(default=0)
    days_of_inventory = models.IntegerField(default=0)

    # detail: growth & ordering
    growth_rate_pct = models.FloatField(default=0)
    suggested_qty = models.IntegerField(default=0)
    inventory_turnover = models.FloatField(default=0)

    # radar (normalized 0..100)
    sales_norm = models.FloatField(default=0)
    profit_norm = models.FloatField(default=0)
    roi_norm = models.FloatField(default=0)
    sell_through_norm = models.FloatField(default=0)
    turnover_norm = models.FloatField(default=0)

    class Meta:
        ordering = ["-score"]

    def __str__(self):
        return f"{self.product.sku} (v1 {self.status})"
