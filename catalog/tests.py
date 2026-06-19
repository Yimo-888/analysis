"""Unit tests for the pure engine functions and a smoke test for the views."""
from datetime import date, timedelta

from django.test import TestCase

from catalog.models import AnalyticsResult, DailySale, Product
from catalog.services import engine, pricing


class PricingTests(TestCase):
    def test_expected_tier_is_monotonic(self):
        self.assertEqual(pricing.expected_tier(0.1), "T1")
        self.assertEqual(pricing.expected_tier(9.9), "T10")
        # higher cost never maps to a lower tier
        prev = -1
        for cpm in [0.1, 0.5, 1.5, 3.1, 5.0, 7.5, 9.5]:
            idx = pricing.tier_index(pricing.expected_tier(cpm))
            self.assertGreaterEqual(idx, prev)
            prev = idx

    def test_price_positive_and_size_ordered(self):
        self.assertLess(pricing.price("T5", "5ml"), pricing.price("T5", "10ml"))
        self.assertLess(pricing.price("T5", "10ml"), pricing.price("T5", "32ml"))


class DiscountTests(TestCase):
    def _m(self, rank, age, doi):
        return {"portfolio_rank": rank, "liquid_age": age, "days_of_inventory": doi}

    def test_discount_band(self):
        low = engine.discount_for(self._m(10, 0, 0), boundary_rank=65, catalog_size=100)
        high = engine.discount_for(self._m(99, 500, 800), boundary_rank=65, catalog_size=100)
        self.assertGreaterEqual(low, 5)
        self.assertLessEqual(high, 40)
        self.assertGreater(high, low)  # worse SKU is discounted more

    def test_interp_factor_clamps(self):
        bps = [(100, 0), (200, 10), (300, 20)]
        self.assertEqual(engine.interp_factor(50, bps), 0)
        self.assertEqual(engine.interp_factor(400, bps), 20)
        self.assertEqual(engine.interp_factor(150, bps), 5)


class ParetoTests(TestCase):
    def test_dominated_point_excluded(self):
        pts = [(1.0, 0.2, 0.5), (0.2, 1.0, 0.5), (0.4, 0.1, 0.1)]
        flags = engine.pareto_optimal_flags(pts)
        self.assertTrue(flags[0])          # best on the sales axis — not dominated
        self.assertTrue(flags[1])          # best on the profit axis — not dominated
        self.assertFalse(flags[2])         # beaten on every axis by point 0


class PhantomStockoutTests(TestCase):
    """The headline v1→v2 difference: an OOS SKU with stale history."""

    def test_grounded_str_does_not_explode_when_oos(self):
        today = date(2026, 1, 1)
        p = {"sku": "X", "current_inventory": 0, "avg_window_inventory": 50,
             "cost_per_ml": 3.0, "max_size": "10ml", "published_tier": "",
             "lab_qty": 0, "wh_qty": 0, "is_new": False, "liquid_opened_date": None}
        sales = {today - timedelta(days=120 + i): 1 for i in range(40)}  # all old
        m = engine.compute_raw_metrics(p, sales, today)
        # v1 naive divides by current stock (1) → huge; v2 grounds it → bounded < 1
        self.assertGreater(m["naive_sell_through"], 5)
        self.assertLess(m["sell_through_rate"], 1.0)


class EngineRunTests(TestCase):
    def setUp(self):
        today = date(2026, 1, 1)
        for i in range(20):
            p = Product.objects.create(
                sku=f"S{i:02d}", name=f"Item {i}", brand="B",
                cost_per_ml=1.0 + i * 0.3, max_size="10ml",
                current_inventory=10, avg_window_inventory=20,
                lab_qty=10, wh_qty=0, is_new=False,
                liquid_opened_date=today - timedelta(days=100),
            )
            for d in range(0, 60, 2):
                DailySale.objects.create(product=p, date=today - timedelta(days=d), units=(i % 3) + 1)

    def test_run_writes_one_result_per_product(self):
        summary = engine.run_engine(run_date=date(2026, 1, 1))
        self.assertEqual(summary["products"], 20)
        self.assertEqual(AnalyticsResult.objects.count(), 20)
        ranks = sorted(AnalyticsResult.objects.values_list("portfolio_rank", flat=True))
        self.assertEqual(ranks, list(range(1, 21)))  # dense, unique ranks


class ViewSmokeTests(TestCase):
    def setUp(self):
        today = date(2026, 1, 1)
        for i in range(15):
            p = Product.objects.create(
                sku=f"V{i:02d}", name=f"V {i}", brand="B", cost_per_ml=2.0,
                max_size="10ml", current_inventory=5, avg_window_inventory=10,
                lab_qty=5, wh_qty=0, liquid_opened_date=today - timedelta(days=400))
            for d in range(0, 30, 3):
                DailySale.objects.create(product=p, date=today - timedelta(days=d), units=1)
        engine.run_engine(run_date=today)

    def test_pages_load(self):
        for url in ["/", "/catalog/", "/pricing/", "/mispricing/", "/evolution/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        sku = Product.objects.first().sku
        self.assertEqual(self.client.get(f"/sku/{sku}/").status_code, 200)
