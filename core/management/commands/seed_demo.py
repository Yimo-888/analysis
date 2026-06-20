"""
Generate a synthetic catalog + ~1 year of daily sales, then run the engine.

Fully reproducible (fixed RNG seed), no real data. A handful of edge cases are
planted so every category/tier is populated and the analytics "design evolution"
comparison has concrete, repeatable examples.

    python manage.py seed_demo            # ~500 SKUs
    python manage.py seed_demo --skus 800
    python manage.py seed_demo --no-run   # seed only, skip the engine
"""
import math
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import AnalyticsResult, DailySale, Product
from core.services import pricing
from core.services.run import run_engine

BRANDS = [
    "Aurelia", "Noctis", "Maison Lume", "Cendre", "Orris House", "Saffron Road",
    "Bois Neuf", "Atlas Parfums", "Solene", "Ember Lab", "Indigo Mer", "Caldera",
    "Lunaire", "Sable", "Verdant", "Petrichor & Co", "Vael", "Lior",
]
NOTES = [
    "Oud", "Amber", "Vetiver", "Bergamot", "Saffron", "Rose", "Cedar", "Musk",
    "Tobacco", "Leather", "Iris", "Neroli", "Patchouli", "Sandalwood", "Vanilla",
    "Cardamom", "Fig", "Tonka", "Incense", "Jasmine", "Smoke", "Sea Salt",
]
SIZES = ["5ml", "10ml", "32ml"]
HORIZON = 365


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
    help = "Seed a synthetic catalog and run the analytics engine."

    def add_arguments(self, parser):
        parser.add_argument("--skus", type=int, default=500)
        parser.add_argument("--no-run", action="store_true")

    def handle(self, *args, **opts):
        rng = random.Random(42)
        today = date.today()
        n = opts["skus"]

        self.stdout.write("Clearing existing data ...")
        AnalyticsResult.objects.all().delete()
        DailySale.objects.all().delete()
        Product.objects.all().delete()

        products, sales = [], []

        def add_product(sku, name, brand, cost_per_ml, size, avg_inv, current_inv,
                        lab, wh, liquid_age, is_new, published_tier, sales_series):
            products.append(Product(
                sku=sku, name=name, brand=brand, cost_per_ml=round(cost_per_ml, 2),
                max_size=size, published_tier=published_tier,
                current_inventory=current_inv, lab_qty=lab, wh_qty=wh,
                avg_window_inventory=round(avg_inv, 1),
                liquid_opened_date=(today - timedelta(days=liquid_age)) if liquid_age is not None else None,
                is_new=is_new, created_at=today - timedelta(days=rng.randint(40, 720)),
            ))
            for day_offset, units in sales_series:
                if units > 0:
                    sales.append((sku, today - timedelta(days=day_offset), units))

        for i in range(n):
            brand = rng.choice(BRANDS)
            name = f"{rng.choice(NOTES)} {rng.choice(NOTES)}"
            code = "".join(w[0] for w in brand.split())[:3].upper()
            sku = f"{code}-{i:04d}"
            lam = math.exp(rng.gauss(-1.6, 1.0))
            cost_per_ml = min(max(round(math.exp(rng.gauss(0.2, 0.9)), 2), 0.2), 9.5)
            size = rng.choice(SIZES)
            avg_inv = max(1.0, lam * rng.uniform(25, 90))
            in_stock = rng.random() > 0.10
            current_inv = int(avg_inv * rng.uniform(0.0, 1.4)) if in_stock else 0
            lab = int(current_inv * rng.uniform(0.4, 1.0))
            wh = current_inv - lab
            liquid_age = rng.randint(20, 520) if lab > 0 else None
            is_new = rng.random() < 0.06
            exp_tier = pricing.expected_tier(cost_per_ml)
            published_tier = "T1" if (rng.random() < 0.05 and exp_tier != "T1") else exp_tier
            series = [(d, knuth_poisson(rng, lam)) for d in range(HORIZON)]
            add_product(sku, name, brand, cost_per_ml, size, avg_inv, current_inv,
                        lab, wh, liquid_age, is_new, published_tier, series)

        self._plant(rng, add_product, today)

        self.stdout.write(f"Inserting {len(products)} products and {len(sales)} sale rows ...")
        with transaction.atomic():
            Product.objects.bulk_create(products, batch_size=500)
            id_by_sku = dict(Product.objects.values_list("sku", "id"))
            DailySale.objects.bulk_create(
                [DailySale(product_id=id_by_sku[sku], date=dt, units=u) for sku, dt, u in sales],
                batch_size=2000)

        if opts["no_run"]:
            self.stdout.write(self.style.SUCCESS("Seeded (engine not run)."))
            return

        self.stdout.write("Running the analytics engine ...")
        summary = run_engine(run_date=today)
        self.stdout.write(self.style.SUCCESS(
            f"Done. {summary['products']} SKUs analyzed, boundary rank "
            f"{summary['boundary_rank']}, {summary['mispriced']} mispriced flagged."))

    def _plant(self, rng, add_product, today):
        # 1) PHANTOM-OOS: strong history, out of stock the last ~45 days.
        series = [(d, 0 if d < 45 else knuth_poisson(rng, 1.4)) for d in range(HORIZON)]
        add_product("DEMO-PHANTOM", "Oud Saffron (phantom-OOS)", "Aurelia", 3.2, "10ml",
                    avg_inv=60, current_inv=0, lab=0, wh=0, liquid_age=None, is_new=False,
                    published_tier=pricing.expected_tier(3.2), sales_series=series)
        # 2) DOOMED-OVERSTOCK: lots of aging lab liquid, barely sells.
        series = [(d, knuth_poisson(rng, 0.05)) for d in range(HORIZON)]
        add_product("DEMO-DOOMED", "Tobacco Leather (doomed overstock)", "Cendre", 4.5, "32ml",
                    avg_inv=70, current_inv=64, lab=64, wh=0, liquid_age=395, is_new=False,
                    published_tier=pricing.expected_tier(4.5), sales_series=series)
        # 3) HEALTHY-OLD: same old liquid age, but sells steadily → stays put.
        series = [(d, knuth_poisson(rng, 0.5)) for d in range(HORIZON)]
        add_product("DEMO-HEALTHYOLD", "Iris Cedar (healthy old stock)", "Solene", 2.6, "10ml",
                    avg_inv=12, current_inv=6, lab=6, wh=0, liquid_age=455, is_new=False,
                    published_tier=pricing.expected_tier(2.6), sales_series=series)
        # 4) MISPRICED: expensive juice published at the bottom tier.
        for idx, cpm in enumerate([6.8, 8.4, 5.9], start=1):
            series = [(d, knuth_poisson(rng, 0.4)) for d in range(HORIZON)]
            add_product(f"DEMO-MISPRICE-{idx}", f"Amber Incense (mispriced #{idx})",
                        "Atlas Parfums", cpm, "10ml", avg_inv=20, current_inv=14, lab=10,
                        wh=4, liquid_age=120, is_new=False, published_tier="T1", sales_series=series)
        # 5) SEALED-ONLY dispose candidate rescued to the marketplace.
        series = [(d, knuth_poisson(rng, 0.03)) for d in range(HORIZON)]
        add_product("DEMO-SEALED", "Smoke Vetiver (sealed only)", "Bois Neuf", 1.1, "10ml",
                    avg_inv=30, current_inv=18, lab=0, wh=18, liquid_age=None, is_new=False,
                    published_tier=pricing.expected_tier(1.1), sales_series=series)
