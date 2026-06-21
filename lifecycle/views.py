from collections import Counter

from django.shortcuts import render

from core.models import AnalyticsResult

from .services import TIER_COLORS, TIER_MEANING, TIER_ORDER, discount_components

COLOR_HEX = {
    "primary": "#0d6efd", "success": "#198754", "info": "#0dcaf0",
    "warning": "#ffc107", "danger": "#dc3545", "dark": "#212529",
}


def dashboard(request):
    results = list(AnalyticsResult.objects.select_related("product"))
    if not results:
        return render(request, "lifecycle/dashboard.html", {"empty": True})

    counts = Counter(r.lifecycle_tier for r in results)
    tier_rows = []
    for t in TIER_ORDER:
        color = TIER_COLORS[t]
        tier_rows.append({
            "tier": t, "count": counts.get(t, 0), "color": color, "hex": COLOR_HEX[color],
            "meaning": TIER_MEANING[t],
        })

    capital_at_risk = sum(r.inventory_value for r in results
                          if r.lifecycle_tier in {"LIQUIDATE", "DISPOSE"})
    return render(request, "lifecycle/dashboard.html", {
        "empty": False,
        "tier_rows": tier_rows,
        "n": len(results),
        "capital_at_risk": capital_at_risk,
        "n_liquidate": counts.get("LIQUIDATE", 0),
        "n_dispose": counts.get("DISPOSE", 0),
    })


def clearance(request):
    liquidating = list(AnalyticsResult.objects.select_related("product")
                       .filter(lifecycle_tier="LIQUIDATE").order_by("-discount_pct", "portfolio_rank"))
    n_all = AnalyticsResult.objects.count()
    rows = []
    for r in liquidating:
        bd = discount_components(r.portfolio_rank / max(n_all, 1),
                                 r.shelf_age_days, r.days_of_inventory)
        rows.append({"r": r, "breakdown": bd})
    return render(request, "lifecycle/clearance.html", {
        "rows": rows,
        "n": len(rows),
        "website": sum(1 for r in liquidating if r.liquidation_strategy == "WEBSITE_DISCOUNT"),
        "marketplace": sum(1 for r in liquidating if r.liquidation_strategy == "MARKETPLACE"),
    })
