from django.shortcuts import render

from .models import AnalyticsResult, Product

# The four feature apps, described for the landing page.
APPS = [
    {
        "name": "Analytics", "badge": "v1", "url": "analytics:dashboard", "icon": "bi-graph-up",
        "tagline": "The original, textbook design.",
        "blurb": "Normalizes sales / profit / ROI, finds the Pareto-optimal frontier, "
                 "and scores on a fixed weighting. Elegant — and it broke on real data.",
        "color": "secondary",
    },
    {
        "name": "DX Analytics", "badge": "v2", "url": "dx_analytics:dashboard", "icon": "bi-bar-chart-line",
        "tagline": "The production rewrite the company adopted.",
        "blurb": "Grounds sell-through in average inventory, ranks the catalog, and runs an "
                 "8-way category cascade that survives messy operational data.",
        "color": "success",
    },
    {
        "name": "Automation", "badge": "", "url": "automation:overview", "icon": "bi-lightning-charge",
        "tagline": "One-click marketplace listing posting.",
        "blurb": "Processes the whole catalog in one run — explodes each base SKU into variant "
                 "listings (variant type × pack size), generates each SKU and title, and posts "
                 "them in bulk batch jobs with per-item status tracking.",
        "color": "primary",
    },
    {
        "name": "Lifecycle", "badge": "", "url": "lifecycle:dashboard", "icon": "bi-arrow-repeat",
        "tagline": "A 6-tier state machine + clearance-pricing engine.",
        "blurb": "Routes each SKU through NEW → STAR → CORE → WATCH → LIQUIDATE → DISPOSE, and "
                 "computes a multi-factor clearance discount for aging, perishable stock.",
        "color": "info",
    },
]


def home(request):
    has_data = AnalyticsResult.objects.exists()
    ctx = {
        "apps": APPS,
        "has_data": has_data,
        "n_products": Product.objects.count(),
    }
    return render(request, "core/home.html", ctx)
