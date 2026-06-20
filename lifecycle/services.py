"""
lifecycle — the product-lifecycle state machine + clearance-discount engine.

Maps each v2 category to one of six tiers and, for challenged SKUs, routes by
where the stock physically sits (aging perishable "lab" liquid vs. sealed
warehouse vs. nothing). Website liquidations get a multi-factor markdown.
"""
from core.services.metrics import interp_factor

LIQUIDATE_LIQUID_AGE = 365     # aging lab liquid starts clearing
DISPOSE_LIQUID_AGE = 540       # spoiled — write off

TIER_ORDER = ["NEW", "STAR", "CORE", "WATCH", "LIQUIDATE", "DISPOSE"]
TIER_COLORS = {
    "NEW": "primary", "STAR": "success", "CORE": "info",
    "WATCH": "warning", "LIQUIDATE": "danger", "DISPOSE": "dark",
}
TIER_MEANING = {
    "NEW": "Grace period — no automated decisions yet.",
    "STAR": "Top performer — restock priority, full price.",
    "CORE": "Solid performer — the healthy default.",
    "WATCH": "Purchasing frozen — sell through what's on hand at full price.",
    "LIQUIDATE": "Actively clearing — website markdown and/or marketplace.",
    "DISPOSE": "Terminal — written off / removed.",
}

_SIMPLE = {
    "New High Performer": ("NEW", ""),
    "High-Demand Rare Item": ("STAR", ""),
    "Core Portfolio": ("CORE", ""),
    "Standard": ("CORE", ""),
    "Slow Mover": ("WATCH", ""),
    "Slow Mover/Watch": ("WATCH", ""),
}

# discount factor breakpoints (illustrative)
_RANK_BP = [(0.60, 0), (0.75, 10), (0.90, 20), (1.0, 30)]
_AGE_BP = [(120, 0), (240, 10), (365, 20), (480, 30)]
_OVER_BP = [(120, 0), (240, 10), (480, 20), (720, 30)]


def resolve_lifecycle(category, m):
    """(tier, strategy) — strategy is the liquidation channel where relevant."""
    if category in _SIMPLE:
        return _SIMPLE[category]

    age, lab, wh = m["liquid_age"], m["lab_qty"], m["wh_qty"]
    if category == "Liquidate Candidate":
        if lab > 0 and age is not None and age > LIQUIDATE_LIQUID_AGE:
            return "LIQUIDATE", "WEBSITE_DISCOUNT"
        if lab > 0:
            return "WATCH", ""              # fresh liquid — hold at full price
        if wh > 0:
            return "LIQUIDATE", "EBAY"      # sealed only — move on the marketplace
        return "WATCH", ""
    # Dispose Candidate
    if lab > 0 and age is not None and age > DISPOSE_LIQUID_AGE:
        return "DISPOSE", ""                # spoiled
    if wh > 0:
        return "LIQUIDATE", "EBAY"          # rescue sealed stock before writing off
    if lab > 0:
        return "LIQUIDATE", "WEBSITE_DISCOUNT"
    return "DISPOSE", ""


def discount_components(rank_ratio, liquid_age, days_of_inventory):
    rank_f = interp_factor(rank_ratio, _RANK_BP)
    age_f = interp_factor(liquid_age or 0, _AGE_BP)
    over_f = interp_factor(days_of_inventory, _OVER_BP)
    return {
        "base": 10,
        "rank_f": round(rank_f, 1), "rank_w": round(0.30 * rank_f, 2),
        "age_f": round(age_f, 1), "age_w": round(0.30 * age_f, 2),
        "over_f": round(over_f, 1), "over_w": round(0.40 * over_f, 2),
    }


def discount_for(m, catalog_size):
    c = discount_components(m["portfolio_rank"] / max(catalog_size, 1),
                            m["liquid_age"], m["days_of_inventory"])
    raw = c["base"] + c["rank_w"] + c["age_w"] + c["over_w"]
    return int(round(max(5, min(40, raw))))


def enrich_lifecycle(rows):
    catalog_size = len(rows)
    for r in rows:
        tier, strategy = resolve_lifecycle(r["category"], r)
        r["lifecycle_tier"] = tier
        r["liquidation_strategy"] = strategy
        r["discount_pct"] = discount_for(r, catalog_size) if strategy in {
            "WEBSITE_DISCOUNT", "BOTH"} else 0
