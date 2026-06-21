from datetime import timedelta

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from core.models import AnalyticsResult, DailySale, Product

from .models import ProductStats

SORTS = {
    "score": ("-score", "Score (High to Low)"),
    "profit": ("-total_profit", "Profit (High to Low)"),
    "roi": ("-roi_pct", "ROI (High to Low)"),
    "daily": ("-daily_sales", "Daily Sales (High to Low)"),
    "days": ("days_supply", "Days Supply (Low to High)"),
}
TREND_WINDOWS = [3, 7, 15, 30, 45, 60, 90, 120, 180, 365]


def dashboard(request):
    qs = ProductStats.objects.select_related("product")
    if not qs.exists():
        return render(request, "analytics/dashboard.html", {"empty": True})

    everything = list(qs)
    total_products = len(everything)
    pareto_optimal = sum(1 for s in everything if s.is_pareto)
    total_inventory = sum(s.stock for s in everything)
    average_roi = sum(s.roi_pct for s in everything) / total_products if total_products else 0

    top_profit = sorted(everything, key=lambda s: s.total_profit, reverse=True)[:12]
    top_roi = sorted(everything, key=lambda s: s.roi_pct, reverse=True)[:12]

    # filters / sort for the table
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", "score")
    order_field = SORTS.get(sort, SORTS["score"])[0]
    table = qs
    if q:
        table = table.filter(product__sku__icontains=q) | table.filter(product__name__icontains=q)
    if status:
        table = table.filter(status=status)
    table = list(table.order_by(order_field)[:300])

    # v1 → v2 design-evolution callout (kept compact)
    cases = []
    for sku in ["DEMO-PHANTOM", "DEMO-DOOMED", "DEMO-HEALTHYOLD"]:
        r = AnalyticsResult.objects.select_related("product").filter(product__sku=sku).first()
        if r:
            cases.append(r)

    return render(request, "analytics/dashboard.html", {
        "empty": False,
        "total_products": total_products,
        "pareto_optimal": pareto_optimal,
        "total_inventory": total_inventory,
        "average_roi": average_roi,
        "top_profit": [{"label": s.product.sku, "value": round(s.total_profit, 2)} for s in top_profit],
        "top_roi": [{"label": s.product.sku, "value": round(s.roi_pct, 2)} for s in top_roi],
        "table": table,
        "q": q, "status": status, "sort": sort,
        "sort_label": SORTS.get(sort, SORTS["score"])[1],
        "sorts": [(k, v[1]) for k, v in SORTS.items()],
        "cases": cases,
    })


def product_json(request, sku):
    """Data for the per-product detail modal (sales trend, inventory, radar, metrics)."""
    product = get_object_or_404(Product, sku=sku)
    s = get_object_or_404(ProductStats, product=product)

    cutoff = s.run_date - timedelta(days=365)
    sales = {x.date: x.units for x in product.sales.filter(date__gt=cutoff)}
    trend = []
    for w in TREND_WINDOWS:
        start = s.run_date - timedelta(days=w)
        total = sum(u for d, u in sales.items() if start < d <= s.run_date)
        trend.append(round(total / w, 2))

    return JsonResponse({
        "name": product.name,
        "sku": product.sku,
        "trend": {"labels": [f"{w}d" for w in TREND_WINDOWS], "values": trend},
        "inventory": {"current": s.stock, "safety": s.safety_stock, "reorder": s.reorder_point},
        "radar": {
            "labels": ["Sales", "Profit", "ROI", "Sell-Through", "Turnover"],
            "values": [s.sales_norm, s.profit_norm, s.roi_norm, s.sell_through_norm, s.turnover_norm],
        },
        "metrics": {
            "weighted_daily_sales": s.daily_sales,
            "profit_per_day": s.profit_per_day,
            "sell_through_pct": s.sell_through_pct,
            "current_inventory": s.stock,
            "reorder_point": s.reorder_point,
            "eoq": s.eoq,
            "safety_stock": s.safety_stock,
            "days_of_inventory": s.days_of_inventory,
            "growth_rate_pct": s.growth_rate_pct,
            "suggested_qty": s.suggested_qty,
            "inventory_turnover": s.inventory_turnover,
        },
    })
