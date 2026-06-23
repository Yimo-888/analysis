from collections import Counter
from datetime import timedelta

from django.http import Http404
from django.shortcuts import get_object_or_404, render

from core.models import AnalyticsResult, Product
from core.services import pricing
from lifecycle.services import TIER_COLORS, discount_components

from .services import CATEGORY_COLORS, CATEGORY_ORDER

COLOR_HEX = {
    "primary": "#0d6efd", "success": "#198754", "info": "#0dcaf0",
    "secondary": "#6c757d", "warning": "#ffc107", "danger": "#dc3545", "dark": "#212529",
}
TIERS = ["NEW", "STAR", "CORE", "WATCH", "LIQUIDATE", "DISPOSE"]


def dashboard(request):
    results = list(AnalyticsResult.objects.select_related("product").order_by("portfolio_rank"))
    if not results:
        return render(request, "analytics2/dashboard.html", {"empty": True})

    counts = Counter(r.category for r in results)
    cat_rows = []
    for c in CATEGORY_ORDER:
        if counts.get(c):
            color = CATEGORY_COLORS.get(c, "secondary")
            cat_rows.append({"category": c, "count": counts[c], "color": color, "hex": COLOR_HEX[color]})

    step = max(1, len(results) // 120)
    curve = [{"x": r.portfolio_rank, "y": round(r.portfolio_score, 4)} for r in results[::step]]

    return render(request, "analytics2/dashboard.html", {
        "empty": False,
        "n": len(results),
        "total_inv_value": sum(r.inventory_value for r in results),
        "cat_rows": cat_rows,
        "curve": curve,
        "top_movers": results[:10],
        "cat_colors": CATEGORY_COLORS,
    })


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
    return render(request, "analytics2/catalog.html", {
        "results": results, "total": qs.count(), "shown": len(results),
        "category": category, "tier": tier, "q": q,
        "categories": CATEGORY_ORDER, "tiers": TIERS,
        "cat_colors": CATEGORY_COLORS, "tier_colors": TIER_COLORS,
    })


def sku_detail(request, sku):
    product = get_object_or_404(Product, sku=sku)
    try:
        r = product.result
    except AnalyticsResult.DoesNotExist:
        raise Http404("No analytics for this SKU yet — run the engine.")

    cutoff = r.run_date - timedelta(days=140)
    sales = {s.date: s.units for s in product.sales.filter(date__gt=cutoff)}
    spark = []
    for i in range(140, -1, -1):
        d = r.run_date - timedelta(days=i)
        spark.append({"x": d.isoformat(), "y": sales.get(d, 0)})

    breakdown = None
    if r.discount_pct:
        n = AnalyticsResult.objects.count()
        breakdown = discount_components(r.portfolio_rank / max(n, 1),
                                        r.shelf_age_days, r.days_of_inventory)

    return render(request, "analytics2/sku_detail.html", {
        "p": product, "r": r, "spark": spark,
        "cat_color": CATEGORY_COLORS.get(r.category, "secondary"),
        "tier_color": TIER_COLORS.get(r.lifecycle_tier, "secondary"),
        "breakdown": breakdown,
        "unit_cost": pricing.pack_cost(product.cost_per_unit, product.max_size),
    })
