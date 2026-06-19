"""
Data model for the Catalyst demo.

Three tables are enough to drive the whole engine:

  Product          — one row per SKU (a decanted fragrance vial line)
  DailySale        — one row per SKU per day (the raw demand signal)
  AnalyticsResult  — one row per SKU, written by the engine each run

Everything is synthetic. There are no external systems and no real data.
"""
from django.db import models


class Product(models.Model):
    """A catalog item. Fragrance is just a concrete, intuitive domain: the
    interesting properties are that stock is *perishable* (decanted "lab"
    liquid ages and eventually spoils) and priced off a per-ml cost."""

    sku = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    brand = models.CharField(max_length=80)

    # Cost drivers / pricing
    cost_per_ml = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_size = models.CharField(max_length=8, default="10ml")
    # The price tier the catalog ACTUALLY published this SKU at. The mispricing
    # audit compares this against the tier the cost implies.
    published_tier = models.CharField(max_length=4, blank=True, default="")

    # Inventory snapshot (current) ...
    current_inventory = models.IntegerField(default=0)
    lab_qty = models.IntegerField(default=0)   # decanted / perishable units
    wh_qty = models.IntegerField(default=0)    # sealed warehouse units
    # ... vs. the AVERAGE stock held across the trailing window. v2 grounds
    # sell-through in this; v1 naively used the current snapshot (see engine).
    avg_window_inventory = models.FloatField(default=0)

    # Lifecycle inputs
    liquid_opened_date = models.DateField(null=True, blank=True)  # for liquid age
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
    """Output of one engine run for one product."""

    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="result")
    run_date = models.DateField()

    # ── v2 (production) metrics ──────────────────────────────────────────
    weighted_daily_sales = models.FloatField(default=0)
    sell_through_rate = models.FloatField(default=0)     # grounded in avg inventory
    velocity = models.FloatField(default=0)              # units / day-with-a-sale
    days_of_inventory = models.FloatField(default=0)
    roi = models.FloatField(default=0)
    inventory_value = models.FloatField(default=0)
    portfolio_score = models.FloatField(default=0)
    portfolio_rank = models.IntegerField(default=0)
    category = models.CharField(max_length=40, default="Standard")
    category_reason = models.CharField(max_length=240, blank=True, default="")
    lifecycle_tier = models.CharField(max_length=16, default="CORE")
    liquidation_strategy = models.CharField(max_length=20, blank=True, default="")
    discount_pct = models.IntegerField(default=0)
    liquid_age_days = models.IntegerField(null=True, blank=True)

    # ── v1 (original Pareto design) metrics, for the design-evolution view ─
    naive_sell_through = models.FloatField(default=0)    # units / current snapshot
    sales_norm = models.FloatField(default=0)
    profit_norm = models.FloatField(default=0)
    roi_norm = models.FloatField(default=0)
    score_balanced = models.FloatField(default=0)
    is_pareto_optimal = models.BooleanField(default=False)
    v1_rank = models.IntegerField(default=0)
    v1_verdict = models.CharField(max_length=40, default="")

    # ── mispricing audit ─────────────────────────────────────────────────
    expected_tier = models.CharField(max_length=4, blank=True, default="")
    published_price = models.FloatField(default=0)
    correct_price = models.FloatField(default=0)
    mispriced = models.BooleanField(default=False)
    mispricing_severity = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        ordering = ["portfolio_rank"]

    def __str__(self):
        return f"{self.product.sku} → {self.category} ({self.lifecycle_tier})"
