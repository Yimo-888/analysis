from collections import Counter
from datetime import timedelta

from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import AnalyticsResult, DailySale, Product
from .services import engine
from .services import pricing as pricing_svc  # aliased: a view below is named pricing()

CATEGORY_ORDER = [
    "New High Performer", "High-Demand Rare Item", "Core Portfolio", "Standard",
    "Slow Mover", "Slow Mover/Watch", "Liquidate Candidate", "Dispose Candidate",
]
# Bootstrap contextual color → hex, so Chart.js and badges agree.
COLOR_HEX = {
    "primary": "#0d6efd", "success": "#198754", "info": "#0dcaf0",
    "secondary": "#6c757d", "warning": "#ffc107", "danger": "#dc3545",
    "dark": "#212529",
}


def _has_data():
    return AnalyticsResult.objects.exists()


def dashboard(request):
    results = list(
        AnalyticsResult.objects.select_related("product").order_by("portfolio_rank")
    )
    if not results:
        return render(request, "catalog/empty.html")

    counts = Counter(r.category for r in results)
    cat_rows = []
    for c in CATEGORY_ORDER:
        if counts.get(c):
            color = engine.CATEGORY_COLORS.get(c, "secondary")
            cat_rows.append({"category": c, "count": counts[c],
                             "color": color, "hex": COLOR_HEX[color]})

    tier_counts = Counter(r.lifecycle_tier for r in results)

    total_inv_value = sum(r.inventory_value for r in results)
    liquidating = [r for r in results if r.lifecycle_tier == "LIQUIDATE"]
    capital_at_risk = sum(r.inventory_value for r in results
                          if r.lifecycle_tier in {"LIQUIDATE", "DISPOSE"})

    # Power-law curve: portfolio_score vs rank, downsampled for the chart.
    step = max(1, len(results) // 120)
    curve = [{"x": r.portfolio_rank, "y": round(r.portfolio_score, 4)}
             for r in results[::step]]

    context = {
        "n": len(results),
        "cat_rows": cat_rows,
        "tier_counts": [(t, tier_counts.get(t, 0)) for t in
                        ["NEW", "STAR", "CORE", "WATCH", "LIQUIDATE", "DISPOSE"]],
        "tier_colors": engine.TIER_COLORS,
        "total_inv_value": total_inv_value,
        "capital_at_risk": capital_at_risk,
        "n_mispriced": sum(1 for r in results if r.mispriced),
        "n_liquidating": len(liquidating),
        "top_movers": results[:10],
        "curve": curve,
        "cat_colors": engine.CATEGORY_COLORS,
    }
    return render(request, "catalog/dashboard.html", context)


def catalog_list(request):
    qs = AnalyticsResult.objects.select_related("product").order_by("portfolio_rank")
    category = request.GET.get("category", "")
    tier = request.GET.get("tier", "")
    q = request.GET.get("q", "").strip()
    if category:
        qs = qs.filter(category=category)
    if tier:
        qs = qs.filter(lifecycle_tier=tier)
    if q:
        qs = qs.filter(product__sku__icontains=q) | qs.filter(product__name__icontains=q)

    results = list(qs[:400])
    return render(request, "catalog/catalog.html", {
        "results": results,
        "total": qs.count(),
        "shown": len(results),
        "category": category,
        "tier": tier,
        "q": q,
        "categories": CATEGORY_ORDER,
        "tiers": ["NEW", "STAR", "CORE", "WATCH", "LIQUIDATE", "DISPOSE"],
        "cat_colors": engine.CATEGORY_COLORS,
        "tier_colors": engine.TIER_COLORS,
    })


def sku_detail(request, sku):
    product = get_object_or_404(Product, sku=sku)
    try:
        r = product.result
    except AnalyticsResult.DoesNotExist:
        raise Http404("No analytics for this SKU yet — run the engine.")

    # Daily sales sparkline for the trailing ~140 days.
    cutoff = r.run_date - timedelta(days=140)
    sales = {s.date: s.units for s in product.sales.filter(date__gt=cutoff)}
    spark = []
    for i in range(140, -1, -1):
        d = r.run_date - timedelta(days=i)
        spark.append({"x": d.isoformat(), "y": sales.get(d, 0)})

    breakdown = _discount_breakdown(r) if r.discount_pct else None
    size = product.max_size
    return render(request, "catalog/sku_detail.html", {
        "p": product,
        "r": r,
        "spark": spark,
        "cat_color": engine.CATEGORY_COLORS.get(r.category, "secondary"),
        "tier_color": engine.TIER_COLORS.get(r.lifecycle_tier, "secondary"),
        "breakdown": breakdown,
        "unit_cost": pricing_svc.unit_cost(product.cost_per_ml, size),
    })


def pricing(request):
    liquidating = list(
        AnalyticsResult.objects.select_related("product")
        .filter(lifecycle_tier="LIQUIDATE").order_by("-discount_pct", "portfolio_rank")
    )
    rows = []
    for r in liquidating:
        rows.append({"r": r, "breakdown": _discount_breakdown(r)})
    return render(request, "catalog/pricing.html", {
        "rows": rows,
        "n": len(rows),
        "website": sum(1 for r in liquidating if r.liquidation_strategy == "WEBSITE_DISCOUNT"),
        "ebay": sum(1 for r in liquidating if r.liquidation_strategy == "EBAY"),
    })


def mispricing(request):
    flagged = list(
        AnalyticsResult.objects.select_related("product")
        .filter(mispriced=True).order_by("-correct_price")
    )
    total_gap = sum((r.correct_price - r.published_price) * max(r.product.current_inventory, 0)
                    for r in flagged)
    return render(request, "catalog/mispricing.html", {
        "flagged": flagged,
        "n": len(flagged),
        "total_gap": total_gap,
    })


def evolution(request):
    results = list(AnalyticsResult.objects.select_related("product"))
    # Pareto scatter: sales_norm (x) vs profit_norm (y), frontier highlighted.
    frontier = [{"x": round(r.sales_norm, 4), "y": round(r.profit_norm, 4)}
                for r in results if r.is_pareto_optimal]
    interior = [{"x": round(r.sales_norm, 4), "y": round(r.profit_norm, 4)}
                for r in results if not r.is_pareto_optimal]

    # Concrete v1-vs-v2 disagreements (the planted SKUs).
    cases = []
    for sku in ["DEMO-PHANTOM", "DEMO-DOOMED", "DEMO-HEALTHYOLD"]:
        r = AnalyticsResult.objects.select_related("product").filter(product__sku=sku).first()
        if r:
            cases.append(r)

    return render(request, "catalog/evolution.html", {
        "frontier": frontier,
        "interior": interior,
        "n_frontier": len(frontier),
        "n_total": len(results),
        "cases": cases,
        "cat_colors": engine.CATEGORY_COLORS,
    })


def _discount_breakdown(r):
    """Recompute the discount factor components for display."""
    n = AnalyticsResult.objects.count()
    boundary = round(n * engine.GROUP2_BOUNDARY_FRACTION)
    rank_ratio = r.portfolio_rank / max(n, 1)
    rank_f = engine.interp_factor(rank_ratio, [(0.60, 0), (0.75, 10), (0.90, 20), (1.0, 30)])
    age_f = engine.interp_factor(r.liquid_age_days or 0, [(120, 0), (240, 10), (365, 20), (480, 30)])
    over_f = engine.interp_factor(r.days_of_inventory, [(120, 0), (240, 10), (480, 20), (720, 30)])
    return {
        "rank_f": round(rank_f, 1), "rank_w": round(0.30 * rank_f, 2),
        "age_f": round(age_f, 1), "age_w": round(0.30 * age_f, 2),
        "over_f": round(over_f, 1), "over_w": round(0.40 * over_f, 2),
        "base": 10,
    }
