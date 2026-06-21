"""
Generate a synthetic catalog + ~1 year of daily sales, run the engine, and
generate the automated listing-posting jobs.

Fully reproducible (fixed RNG seed), no real data — generic SKUs only. A handful
of edge cases are planted so every category/tier is populated and the analytics
v1-vs-v2 comparison has concrete, repeatable examples.

    python manage.py seed_demo            # ~1,200 SKUs
    python manage.py seed_demo --skus 400
    python manage.py seed_demo --no-run   # seed data only, skip the engine
"""
import math
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from automation.models import Listing, PostingJob
from automation.services import expand
from core.models import AnalyticsResult, DailySale, Product
from core.services.pricing import SIZES
from core.services.run import run_engine

HORIZON = 365
# pack sizes weighted toward the small/base size
SIZE_POOL = ["S", "S", "S", "M", "M", "L", "XL", "2XL", "BULK"]
FAIL_REASONS = [
    "image generation timed out", "duplicate SKU rejected by marketplace",
    "missing required attribute", "price validation failed",
    "marketplace API 429 (rate limited)",
]


def knuth_poisson(rng, lam):
    if lam <= 0:
        return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


class Command(BaseCommand):
    help = "Seed a synthetic catalog, run the engine, and generate listing-posting jobs."

    def add_arguments(self, parser):
        parser.add_argument("--skus", type=int, default=1200)
        parser.add_argument("--no-run", action="store_true")

    def handle(self, *args, **opts):
        rng = random.Random(42)
        today = date.today()
        n = opts["skus"]

        self.stdout.write("Clearing existing data ...")
        Listing.objects.all().delete()
        PostingJob.objects.all().delete()
        AnalyticsResult.objects.all().delete()
        DailySale.objects.all().delete()
        Product.objects.all().delete()

        products, sales = [], []

        def add_product(sku, name, brand, cost_per_unit, size, avg_inv, current_inv,
                        open_q, sealed, shelf_age, is_new, sales_series):
            products.append(Product(
                sku=sku, name=name, brand=brand, cost_per_unit=round(cost_per_unit, 2),
                max_size=size, current_inventory=current_inv, open_qty=open_q, sealed_qty=sealed,
                avg_window_inventory=round(avg_inv, 1),
                opened_date=(today - timedelta(days=shelf_age)) if shelf_age is not None else None,
                is_new=is_new, created_at=today - timedelta(days=rng.randint(40, 720)),
            ))
            for day_offset, units in sales_series:
                if units > 0:
                    sales.append((sku, today - timedelta(days=day_offset), units))

        for i in range(1, n + 1):
            sku = f"SKU-{i:04d}"
            name = f"Product {i:04d}"
            brand = f"Vendor {(i % 24) + 1:02d}"
            size = rng.choice(SIZE_POOL)
            lam = math.exp(rng.gauss(1.4, 1.2))              # ~4/day median, top sellers ~50-100
            cost_per_unit = min(max(round(math.exp(rng.gauss(0.3, 0.7)), 2), 0.3), 6.0)
            avg_inv = max(5.0, lam * rng.uniform(45, 110))
            in_stock = rng.random() > 0.08
            current_inv = int(avg_inv * rng.uniform(0.15, 1.3)) if in_stock else 0
            open_q = int(current_inv * rng.uniform(0.4, 1.0))
            sealed = current_inv - open_q
            shelf_age = rng.randint(20, 520) if open_q > 0 else None
            is_new = rng.random() < 0.06
            series = [(d, knuth_poisson(rng, lam)) for d in range(HORIZON)]
            add_product(sku, name, brand, cost_per_unit, size, avg_inv, current_inv,
                        open_q, sealed, shelf_age, is_new, series)

        self._plant(rng, add_product)

        self.stdout.write(f"Inserting {len(products)} products and {len(sales)} sale rows ...")
        with transaction.atomic():
            Product.objects.bulk_create(products, batch_size=500)
            id_by_sku = dict(Product.objects.values_list("sku", "id"))
            DailySale.objects.bulk_create(
                [DailySale(product_id=id_by_sku[sku], date=dt, units=u) for sku, dt, u in sales],
                batch_size=2000)

        self.stdout.write("Generating listing-posting jobs ...")
        n_jobs, n_listings, n_bases = self._seed_listings(rng, today)
        self.stdout.write(f"  {n_jobs} jobs, {n_listings} listings from {n_bases} products.")

        if opts["no_run"]:
            self.stdout.write(self.style.SUCCESS("Seeded (engine not run)."))
            return

        self.stdout.write("Running the analytics engine ...")
        summary = run_engine(run_date=today)
        self.stdout.write(self.style.SUCCESS(
            f"Done. {summary['products']} SKUs analyzed, boundary rank "
            f"{summary['boundary_rank']}."))

    # ── planted analytics edge cases ────────────────────────────────────
    def _plant(self, rng, add_product):
        series = [(d, 0 if d < 45 else knuth_poisson(rng, 1.4)) for d in range(HORIZON)]
        add_product("DEMO-PHANTOM", "Demo — phantom stockout", "Vendor 01", 3.2, "S",
                    avg_inv=60, current_inv=0, open_q=0, sealed=0, shelf_age=None,
                    is_new=False, sales_series=series)
        series = [(d, knuth_poisson(rng, 0.05)) for d in range(HORIZON)]
        add_product("DEMO-DOOMED", "Demo — doomed overstock", "Vendor 02", 4.5, "BULK",
                    avg_inv=70, current_inv=64, open_q=64, sealed=0, shelf_age=395,
                    is_new=False, sales_series=series)
        series = [(d, knuth_poisson(rng, 0.5)) for d in range(HORIZON)]
        add_product("DEMO-HEALTHYOLD", "Demo — healthy aged stock", "Vendor 03", 2.6, "S",
                    avg_inv=12, current_inv=6, open_q=6, sealed=0, shelf_age=455,
                    is_new=False, sales_series=series)
        series = [(d, knuth_poisson(rng, 0.03)) for d in range(HORIZON)]
        add_product("DEMO-SEALED", "Demo — sealed-only stock", "Vendor 04", 1.1, "S",
                    avg_inv=30, current_inv=18, open_q=0, sealed=18, shelf_age=None,
                    is_new=False, sales_series=series)

    # ── automated listing posting ───────────────────────────────────────
    def _seed_listings(self, rng, today):
        """Fan a large sample of the catalog out into variant listings across batch jobs,
        to show the pipeline operating at scale."""
        bases = list(Product.objects.exclude(sku__startswith="DEMO-").order_by("id")[:600])
        job_specs = [
            ("Nightly catalog run — Mon", PostingJob.COMPLETED, 6),
            ("Nightly catalog run — Tue", PostingJob.COMPLETED, 5),
            ("Nightly catalog run — Wed", PostingJob.COMPLETED, 4),
            ("Nightly catalog run — Thu", PostingJob.COMPLETED, 3),
            ("Nightly catalog run — Fri", PostingJob.COMPLETED, 1),
            ("Today's run (in progress)", PostingJob.PROCESSING, 0),
        ]
        per_job = max(1, len(bases) // len(job_specs))
        jobs, listings = [], []
        for j, (name, status, days_ago) in enumerate(job_specs):
            job = PostingJob.objects.create(
                name=name, status=status, marketplace="Marketplace",
                created_on=today - timedelta(days=days_ago))
            jobs.append(job)
            chunk = bases[j * per_job:(j + 1) * per_job]
            for base in chunk:
                for variant_sku, variant_type, size, title in expand(base):
                    listings.append(self._make_listing(rng, job, base, variant_sku,
                                                        variant_type, size, title, status))
        Listing.objects.bulk_create(listings, batch_size=2000)
        return len(jobs), len(listings), len(bases)

    def _make_listing(self, rng, job, base, variant_sku, variant_type, size, title, job_status):
        if job_status == PostingJob.PROCESSING:
            roll = rng.random()
            status = (Listing.POSTED if roll < 0.55 else
                      Listing.FAILED if roll > 0.92 else Listing.PENDING)
        else:
            status = Listing.FAILED if rng.random() < 0.04 else Listing.POSTED
        return Listing(
            job=job, base_product=base, variant_sku=variant_sku, variant_type=variant_type,
            size=size, title=title, status=status,
            failed_reason=(rng.choice(FAIL_REASONS) if status == Listing.FAILED else ""),
            posted_on=(job.created_on if status == Listing.POSTED else None),
        )
