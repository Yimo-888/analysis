"""
Generate a synthetic catalog + ~1 year of daily sales, run the engine, and
generate the automated listing-posting jobs.

Fully reproducible (fixed RNG seed), no real data. A handful of edge cases are
planted so every category/tier is populated and the analytics v1-vs-v2 comparison
has concrete, repeatable examples.

    python manage.py seed_demo            # ~500 SKUs
    python manage.py seed_demo --skus 800
    python manage.py seed_demo --no-run   # seed data only, skip the engine
"""
import math
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from automation.models import Listing, PostingJob
from automation.services import expand
from core.fragrances import FRAGRANCES
from core.models import AnalyticsResult, DailySale, Product
from core.services.run import run_engine

HORIZON = 365
CONC_CODE = {
    "Eau de Parfum": "EDP", "Eau de Toilette": "EDT", "Parfum": "Parfum",
    "Extrait de Parfum": "Extrait", "Elixir": "Elixir", "Cologne": "Cologne",
}
FAIL_REASONS = [
    "image generation timed out", "duplicate SKU rejected by marketplace",
    "missing attribute: concentration", "price validation failed",
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
        parser.add_argument("--no-run", action="store_true")

    def handle(self, *args, **opts):
        rng = random.Random(42)
        today = date.today()

        self.stdout.write("Clearing existing data ...")
        Listing.objects.all().delete()
        PostingJob.objects.all().delete()
        AnalyticsResult.objects.all().delete()
        DailySale.objects.all().delete()
        Product.objects.all().delete()

        products, sales = [], []

        def add_product(sku, name, brand, cost_per_ml, size, avg_inv, current_inv,
                        lab, wh, liquid_age, is_new, sales_series):
            products.append(Product(
                sku=sku, name=name, brand=brand, cost_per_ml=round(cost_per_ml, 2),
                max_size=size, current_inventory=current_inv, lab_qty=lab, wh_qty=wh,
                avg_window_inventory=round(avg_inv, 1),
                liquid_opened_date=(today - timedelta(days=liquid_age)) if liquid_age is not None else None,
                is_new=is_new, created_at=today - timedelta(days=rng.randint(40, 720)),
            ))
            for day_offset, units in sales_series:
                if units > 0:
                    sales.append((sku, today - timedelta(days=day_offset), units))

        # Real fragrance names (public product names) make the catalog look like a
        # real decant shop; every number below is fabricated. Each fragrance is sold
        # as a 1ml decant, with a chance of an extra 2/5ml variant.
        for brand, line, conc, gender in FRAGRANCES:
            short = f"{brand} {line} {CONC_CODE.get(conc, '')}".strip()
            full = f"{brand} {line} {conc} {gender}"
            sizes = ["1ml"]
            if rng.random() < 0.45:
                sizes.append(rng.choice(["2ml", "5ml"]))
            for size in sizes:
                sku = f"{short} {size}"
                lam = math.exp(rng.gauss(1.4, 1.2))            # ~4/day median, top sellers ~50-100
                cost_per_ml = min(max(round(math.exp(rng.gauss(0.3, 0.7)), 2), 0.3), 6.0)
                avg_inv = max(5.0, lam * rng.uniform(45, 110))  # stock in the hundreds–thousands
                in_stock = rng.random() > 0.08
                current_inv = int(avg_inv * rng.uniform(0.15, 1.3)) if in_stock else 0
                lab = int(current_inv * rng.uniform(0.4, 1.0))
                wh = current_inv - lab
                liquid_age = rng.randint(20, 520) if lab > 0 else None
                is_new = rng.random() < 0.06
                series = [(d, knuth_poisson(rng, lam)) for d in range(HORIZON)]
                add_product(sku, full, brand, cost_per_ml, size, avg_inv, current_inv,
                            lab, wh, liquid_age, is_new, series)

        self._plant(rng, add_product)

        self.stdout.write(f"Inserting {len(products)} products and {len(sales)} sale rows ...")
        with transaction.atomic():
            Product.objects.bulk_create(products, batch_size=500)
            id_by_sku = dict(Product.objects.values_list("sku", "id"))
            DailySale.objects.bulk_create(
                [DailySale(product_id=id_by_sku[sku], date=dt, units=u) for sku, dt, u in sales],
                batch_size=2000)

        self.stdout.write("Generating listing-posting jobs ...")
        n_jobs, n_listings = self._seed_listings(rng, today)
        self.stdout.write(f"  {n_jobs} jobs, {n_listings} variant listings.")

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
        add_product("DEMO-PHANTOM", "Oud Saffron (phantom-OOS)", "Aurelia", 3.2, "10ml",
                    avg_inv=60, current_inv=0, lab=0, wh=0, liquid_age=None, is_new=False,
                    sales_series=series)
        series = [(d, knuth_poisson(rng, 0.05)) for d in range(HORIZON)]
        add_product("DEMO-DOOMED", "Tobacco Leather (doomed overstock)", "Cendre", 4.5, "32ml",
                    avg_inv=70, current_inv=64, lab=64, wh=0, liquid_age=395, is_new=False,
                    sales_series=series)
        series = [(d, knuth_poisson(rng, 0.5)) for d in range(HORIZON)]
        add_product("DEMO-HEALTHYOLD", "Iris Cedar (healthy old stock)", "Solene", 2.6, "10ml",
                    avg_inv=12, current_inv=6, lab=6, wh=0, liquid_age=455, is_new=False,
                    sales_series=series)
        series = [(d, knuth_poisson(rng, 0.03)) for d in range(HORIZON)]
        add_product("DEMO-SEALED", "Smoke Vetiver (sealed only)", "Bois Neuf", 1.1, "10ml",
                    avg_inv=30, current_inv=18, lab=0, wh=18, liquid_age=None, is_new=False,
                    sales_series=series)

    # ── automated listing posting ───────────────────────────────────────
    def _seed_listings(self, rng, today):
        """Fan a sample of base products out into variant listings across batch jobs.
        One canonical (1ml) product per fragrance, so fan-out SKUs never collide."""
        bases = list(Product.objects.filter(sku__endswith=" 1ml")
                     .exclude(sku__startswith="DEMO-").order_by("id")[:40])
        job_specs = [
            ("Spring drop — batch 1", PostingJob.COMPLETED, 9),
            ("New arrivals — batch 2", PostingJob.COMPLETED, 6),
            ("Restock variants — batch 3", PostingJob.COMPLETED, 4),
            ("Catalog expansion — batch 4", PostingJob.COMPLETED, 1),
            ("Today's queue — batch 5", PostingJob.PROCESSING, 0),
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
                for variant_sku, bottle_type, size, title in expand(base):
                    listings.append(self._make_listing(rng, job, base, variant_sku,
                                                        bottle_type, size, title, status, today))
        Listing.objects.bulk_create(listings, batch_size=2000)
        return len(jobs), len(listings)

    def _make_listing(self, rng, job, base, variant_sku, bottle_type, size, title, job_status, today):
        if job_status == PostingJob.PROCESSING:
            roll = rng.random()
            status = (Listing.POSTED if roll < 0.55 else
                      Listing.FAILED if roll > 0.92 else Listing.PENDING)
        else:
            status = Listing.FAILED if rng.random() < 0.05 else Listing.POSTED
        return Listing(
            job=job, base_product=base, variant_sku=variant_sku, bottle_type=bottle_type,
            size=size, title=title, status=status,
            failed_reason=(rng.choice(FAIL_REASONS) if status == Listing.FAILED else ""),
            posted_on=(job.created_on if status == Listing.POSTED else None),
        )
