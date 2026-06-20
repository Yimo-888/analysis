from django.shortcuts import render

from core.models import AnalyticsResult


def dashboard(request):
    results = list(AnalyticsResult.objects.select_related("product"))
    if not results:
        return render(request, "analytics/dashboard.html", {"empty": True})

    frontier = [{"x": round(r.sales_norm, 4), "y": round(r.profit_norm, 4)}
                for r in results if r.is_pareto_optimal]
    interior = [{"x": round(r.sales_norm, 4), "y": round(r.profit_norm, 4)}
                for r in results if not r.is_pareto_optimal]
    top = sorted(results, key=lambda r: r.v1_rank)[:12]

    cases = []
    for sku in ["DEMO-PHANTOM", "DEMO-DOOMED", "DEMO-HEALTHYOLD"]:
        c = AnalyticsResult.objects.select_related("product").filter(product__sku=sku).first()
        if c:
            cases.append(c)

    return render(request, "analytics/dashboard.html", {
        "empty": False,
        "frontier": frontier,
        "interior": interior,
        "n_frontier": len(frontier),
        "n_total": len(results),
        "top": top,
        "cases": cases,
    })
