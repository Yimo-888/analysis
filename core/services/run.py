"""
Orchestrator — runs the whole pipeline in dependency order and writes the
shared AnalyticsResult table. Each feature app owns one stage:

    core.metrics → analytics(v1) → dx_analytics(v2) → lifecycle → automation
"""
from datetime import date

from analytics.services import enrich_v1
from automation.services import enrich_pricing
from dx_analytics.services import enrich_v2
from lifecycle.services import enrich_lifecycle

from .metrics import compute_base_metrics


def run_engine(run_date=None):
    from django.db import transaction

    from core.models import AnalyticsResult, DailySale, Product

    products = list(Product.objects.all())
    if not products:
        return {"products": 0}

    sales_index = {}
    for pid, d, units in DailySale.objects.all().values_list("product_id", "date", "units"):
        sales_index.setdefault(pid, {})[d] = units

    ref_date = run_date or _max_sale_date(sales_index) or date.today()

    rows = []
    for p in products:
        pdict = {
            "sku": p.sku, "current_inventory": p.current_inventory,
            "avg_window_inventory": p.avg_window_inventory, "cost_per_ml": p.cost_per_ml,
            "max_size": p.max_size, "published_tier": p.published_tier,
            "lab_qty": p.lab_qty, "wh_qty": p.wh_qty, "is_new": p.is_new,
            "liquid_opened_date": p.liquid_opened_date,
        }
        m = compute_base_metrics(pdict, sales_index.get(p.id, {}), ref_date)
        m["_pid"] = p.id
        rows.append(m)

    # ── pipeline stages (each app enriches the shared rows) ──
    enrich_v1(rows)                 # v1 Pareto + balanced score
    boundary_rank = enrich_v2(rows)  # v2 score, rank, category cascade
    enrich_lifecycle(rows)          # tier + clearance discount
    enrich_pricing(rows)            # pricing audit

    with transaction.atomic():
        AnalyticsResult.objects.all().delete()
        AnalyticsResult.objects.bulk_create([
            AnalyticsResult(
                product_id=r["_pid"], run_date=ref_date,
                weighted_daily_sales=r["weighted_daily_sales"], velocity=r["velocity"],
                days_of_inventory=r["days_of_inventory"], roi=r["roi"],
                inventory_value=r["inventory_value"], liquid_age_days=r["liquid_age"],
                sell_through_rate=r["sell_through_rate"], portfolio_score=r["portfolio_score"],
                portfolio_rank=r["portfolio_rank"], category=r["category"],
                category_reason=r["category_reason"], lifecycle_tier=r["lifecycle_tier"],
                liquidation_strategy=r["liquidation_strategy"], discount_pct=r["discount_pct"],
                naive_sell_through=r["naive_sell_through"], sales_norm=r["sales_norm"],
                profit_norm=r["profit_norm"], roi_norm=r["roi_norm"],
                score_balanced=r["score_balanced"], is_pareto_optimal=r["is_pareto"],
                v1_rank=r["v1_rank"], v1_verdict=r["v1_verdict"],
                expected_tier=r["expected_tier"], published_price=r["published_price"],
                correct_price=r["correct_price"], mispriced=r["mispriced"],
                mispricing_severity=r["mispricing_severity"],
            )
            for r in rows
        ], batch_size=500)

    return {
        "products": len(rows), "run_date": ref_date, "boundary_rank": boundary_rank,
        "mispriced": sum(1 for r in rows if r["mispriced"]),
    }


def _max_sale_date(sales_index):
    best = None
    for by_day in sales_index.values():
        for d in by_day:
            if best is None or d > best:
                best = d
    return best
