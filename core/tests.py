"""Tests spanning the pipeline: core metrics, each app's logic, and views."""
from datetime import date, timedelta

from django.test import TestCase

from analytics.services import pareto_optimal_flags
from automation.models import Listing, PostingJob
from automation.services import VARIANTS_PER_PRODUCT, expand
from core.models import AnalyticsResult, DailySale, Product
from core.services import pricing
from core.services.metrics import compute_base_metrics, interp_factor
from core.services.run import run_engine
from lifecycle.services import discount_for, resolve_lifecycle


class PricingTests(TestCase):
    def test_expected_tier_is_monotonic(self):
        self.assertEqual(pricing.expected_tier(0.1), "T1")
        self.assertEqual(pricing.expected_tier(9.9), "T10")
        prev = -1
        for cpm in [0.1, 0.5, 1.5, 3.1, 5.0, 7.5, 9.5]:
            idx = pricing.tier_index(pricing.expected_tier(cpm))
            self.assertGreaterEqual(idx, prev)
            prev = idx

    def test_price_size_ordered(self):
        self.assertLess(pricing.price("T5", "5ml"), pricing.price("T5", "10ml"))
        self.assertLess(pricing.price("T5", "10ml"), pricing.price("T5", "32ml"))


class ListingFanoutTests(TestCase):
    def test_expand_yields_unique_full_grid(self):
        p = Product.objects.create(sku="B-1", name="Oud Rose", brand="Brand",
                                   cost_per_ml=2.0, max_size="10ml")
        variants = list(expand(p))
        self.assertEqual(len(variants), VARIANTS_PER_PRODUCT)
        skus = [v[0] for v in variants]
        self.assertEqual(len(set(skus)), len(skus))           # unique
        self.assertTrue(all(s.startswith(p.sku) for s in skus))

    def test_job_progress_counts(self):
        job = PostingJob.objects.create(name="J", status=PostingJob.PROCESSING,
                                        created_on=date(2026, 1, 1))
        p = Product.objects.create(sku="B-2", name="X Y", brand="B", cost_per_ml=1.0)
        for i, (vsku, bt, sz, title) in enumerate(expand(p)):
            st = Listing.POSTED if i < 6 else (Listing.FAILED if i == 7 else Listing.PENDING)
            Listing.objects.create(job=job, base_product=p, variant_sku=vsku, bottle_type=bt,
                                   size=sz, title=title, status=st)
        self.assertEqual(job.total, VARIANTS_PER_PRODUCT)
        self.assertEqual(job.posted, 6)
        self.assertEqual(job.failed, 1)
        self.assertEqual(job.progress_pct, round(100 * 6 / VARIANTS_PER_PRODUCT))


class DiscountTests(TestCase):
    def _m(self, rank, age, doi):
        return {"portfolio_rank": rank, "liquid_age": age, "days_of_inventory": doi}

    def test_discount_band_and_monotonicity(self):
        low = discount_for(self._m(10, 0, 0), catalog_size=100)
        high = discount_for(self._m(99, 500, 800), catalog_size=100)
        self.assertGreaterEqual(low, 5)
        self.assertLessEqual(high, 40)
        self.assertGreater(high, low)

    def test_interp_factor_clamps(self):
        bps = [(100, 0), (200, 10), (300, 20)]
        self.assertEqual(interp_factor(50, bps), 0)
        self.assertEqual(interp_factor(400, bps), 20)
        self.assertEqual(interp_factor(150, bps), 5)


class RoutingTests(TestCase):
    def test_sealed_dispose_candidate_rescued_to_ebay(self):
        m = {"liquid_age": None, "lab_qty": 0, "wh_qty": 10}
        self.assertEqual(resolve_lifecycle("Dispose Candidate", m), ("LIQUIDATE", "EBAY"))

    def test_aging_lab_liquid_liquidates(self):
        m = {"liquid_age": 400, "lab_qty": 20, "wh_qty": 0}
        self.assertEqual(resolve_lifecycle("Liquidate Candidate", m), ("LIQUIDATE", "WEBSITE_DISCOUNT"))


class ParetoTests(TestCase):
    def test_dominated_point_excluded(self):
        pts = [(1.0, 0.2, 0.5), (0.2, 1.0, 0.5), (0.4, 0.1, 0.1)]
        flags = pareto_optimal_flags(pts)
        self.assertTrue(flags[0])
        self.assertTrue(flags[1])
        self.assertFalse(flags[2])


class PhantomStockoutTests(TestCase):
    def test_grounded_str_does_not_explode_when_oos(self):
        today = date(2026, 1, 1)
        p = {"sku": "X", "current_inventory": 0, "avg_window_inventory": 50,
             "cost_per_ml": 3.0, "max_size": "10ml", "published_tier": "",
             "lab_qty": 0, "wh_qty": 0, "is_new": False, "liquid_opened_date": None}
        sales = {today - timedelta(days=120 + i): 1 for i in range(40)}
        m = compute_base_metrics(p, sales, today)
        self.assertGreater(m["naive_sell_through"], 5)
        self.assertLess(m["sell_through_rate"], 1.0)


class EngineRunTests(TestCase):
    def setUp(self):
        today = date(2026, 1, 1)
        for i in range(20):
            p = Product.objects.create(
                sku=f"S{i:02d}", name=f"Item {i}", brand="B", cost_per_ml=1.0 + i * 0.3,
                max_size="10ml", current_inventory=10, avg_window_inventory=20,
                lab_qty=10, wh_qty=0, liquid_opened_date=today - timedelta(days=100))
            for d in range(0, 60, 2):
                DailySale.objects.create(product=p, date=today - timedelta(days=d), units=(i % 3) + 1)

    def test_run_writes_dense_ranks_and_v1_stats(self):
        from analytics.models import ProductStats
        summary = run_engine(run_date=date(2026, 1, 1))
        self.assertEqual(summary["products"], 20)
        self.assertEqual(AnalyticsResult.objects.count(), 20)
        self.assertEqual(ProductStats.objects.count(), 20)
        ranks = sorted(AnalyticsResult.objects.values_list("portfolio_rank", flat=True))
        self.assertEqual(ranks, list(range(1, 21)))
        # classical metrics are populated and sane
        s = ProductStats.objects.first()
        self.assertGreaterEqual(s.reorder_point, 0)
        self.assertIn(s.status, {"Optimal", "Optimize"})


class ViewSmokeTests(TestCase):
    def setUp(self):
        today = date(2026, 1, 1)
        for i in range(15):
            p = Product.objects.create(
                sku=f"V{i:02d}", name=f"V {i}", brand="B", cost_per_ml=2.0, max_size="10ml",
                current_inventory=5, avg_window_inventory=10, lab_qty=5, wh_qty=0,
                liquid_opened_date=today - timedelta(days=400))
            for d in range(0, 30, 3):
                DailySale.objects.create(product=p, date=today - timedelta(days=d), units=1)
        run_engine(run_date=today)
        # one posting job + its listings, so the automation pages have data
        job = PostingJob.objects.create(name="Job", status=PostingJob.COMPLETED, created_on=today)
        base = Product.objects.first()
        for vsku, bt, sz, title in expand(base):
            Listing.objects.create(job=job, base_product=base, variant_sku=vsku, bottle_type=bt,
                                   size=sz, title=title, status=Listing.POSTED, posted_on=today)
        self.job_pk = job.pk

    def test_every_app_page_loads(self):
        urls = ["/", "/analytics/", "/dx-analytics/", "/dx-analytics/catalog/",
                "/automation/", f"/automation/jobs/{self.job_pk}/",
                "/lifecycle/", "/lifecycle/clearance/"]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        sku = Product.objects.first().sku
        self.assertEqual(self.client.get(f"/dx-analytics/sku/{sku}/").status_code, 200)
        # analytics detail JSON endpoint (drives the modal)
        resp = self.client.get(f"/analytics/product/{sku}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("metrics", resp.json())
