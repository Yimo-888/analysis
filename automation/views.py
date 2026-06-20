from collections import Counter

from django.shortcuts import render

from core.models import AnalyticsResult
from core.services import pricing as pricing_svc  # aliased: a view below is named pricing()


def pricing(request):
    """The auto-pricing pipeline: cost per ml → tier → published price per size."""
    results = list(AnalyticsResult.objects.select_related("product"))
    tier_table = []
    for t in pricing_svc.TIER_NAMES:
        tier_table.append({
            "tier": t,
            "min_cost": pricing_svc.TIER_MIN_COST_PER_ML[t],
            "p5": pricing_svc.price(t, "5ml"),
            "p10": pricing_svc.price(t, "10ml"),
            "p32": pricing_svc.price(t, "32ml"),
        })

    dist = Counter(r.expected_tier for r in results)
    tier_dist = [{"tier": t, "count": dist.get(t, 0)} for t in pricing_svc.TIER_NAMES]
    n = len(results)
    return render(request, "automation/pricing.html", {
        "tier_table": tier_table,
        "tier_dist": tier_dist,
        "n": n,
        "prices_published": n * len(pricing_svc.SIZES),
        "n_sizes": len(pricing_svc.SIZES),
        "n_mispriced": sum(1 for r in results if r.mispriced),
    })


def mispricing(request):
    flagged = list(AnalyticsResult.objects.select_related("product")
                   .filter(mispriced=True).order_by("-correct_price"))
    total_gap = sum((r.correct_price - r.published_price) * max(r.product.current_inventory, 0)
                    for r in flagged)
    return render(request, "automation/mispricing.html", {
        "flagged": flagged, "n": len(flagged), "total_gap": total_gap,
    })
