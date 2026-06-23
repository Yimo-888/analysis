"""
analytics2 (v2) — the production design the engine actually ships.

Grounds sell-through in *average* inventory, scores and ranks the catalog, then
runs an explicit 8-way category cascade off portfolio-wide percentiles. This is
the version that survives messy operational data.
"""
from core.services.metrics import median, normalizer, percentile

GROUP2_BOUNDARY_FRACTION = 0.65   # rank past this fraction of the catalog = "challenged"

# score weights (v2 house view): demand, then how cleanly it sells, then margin
W_VELOCITY, W_STR, W_ROI = 0.40, 0.30, 0.30

CATEGORY_ORDER = [
    "New High Performer", "High-Demand Rare Item", "Core Portfolio", "Standard",
    "Slow Mover", "Slow Mover/Watch", "Liquidate Candidate", "Dispose Candidate",
]
CATEGORY_COLORS = {
    "New High Performer": "primary", "High-Demand Rare Item": "success",
    "Core Portfolio": "info", "Standard": "secondary",
    "Slow Mover": "warning", "Slow Mover/Watch": "warning",
    "Liquidate Candidate": "danger", "Dispose Candidate": "dark",
}


def categorize(m, stats, boundary_rank):
    rank = m["portfolio_rank"]
    if rank > boundary_rank:
        if m["inventory_value"] > stats["inv_value_p65"]:
            return "Liquidate Candidate", (
                f"Challenged (rank {rank} > {boundary_rank}) with high capital at risk "
                f"(${m['inventory_value']:,.0f}) — clear it down.")
        return "Dispose Candidate", (
            f"Challenged (rank {rank} > {boundary_rank}) with little capital at risk — "
            f"write off rather than discount.")

    if m["is_new"] and m["portfolio_score"] > stats["score_median"]:
        return "New High Performer", "New SKU already above median — protect from demotion."
    if m["current_inventory"] <= 0 and m["days_since_sale"] > 30:
        return "Slow Mover/Watch", (
            f"Out of stock, no sale in {m['days_since_sale']}d — freeze purchasing, "
            f"don't liquidate (may just be temporarily OOS).")
    if m["sell_through_rate"] > stats["str_p75"] and m["roi"] > stats["roi_median"]:
        return "High-Demand Rare Item", "Top-quartile sell-through and above-median ROI."
    if m["is_pareto"]:
        return "Core Portfolio", "On the sales/profit/ROI efficient frontier — a portfolio anchor."
    if (m["current_inventory"] > 0 and m["sell_through_rate"] < stats["str_p25"]
            and m["weighted_daily_sales"] < stats["wds_median"]):
        return "Slow Mover", ("In stock but bottom-quartile sell-through and below-median "
                              "velocity — freeze purchasing, keep selling at full price.")
    return "Standard", "Solid mid-catalog performer."


def enrich_v2(rows):
    """Add v2 fields to each row (in place). Returns the boundary rank."""
    norm_v = normalizer([r["velocity"] for r in rows])
    norm_s = normalizer([r["sell_through_rate"] for r in rows])
    norm_r = normalizer([r["roi"] for r in rows])
    for r in rows:
        r["portfolio_score"] = round(
            W_VELOCITY * norm_v(r["velocity"]) + W_STR * norm_s(r["sell_through_rate"])
            + W_ROI * norm_r(r["roi"]), 4)
    rows.sort(key=lambda r: r["portfolio_score"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["portfolio_rank"] = i

    stats = {
        "roi_median": median([r["roi"] for r in rows]),
        "str_p75": percentile([r["sell_through_rate"] for r in rows], 75),
        "str_p25": percentile([r["sell_through_rate"] for r in rows], 25),
        "wds_median": median([r["weighted_daily_sales"] for r in rows]),
        "inv_value_p65": percentile([r["inventory_value"] for r in rows], 65),
        "score_median": median([r["portfolio_score"] for r in rows]),
    }
    boundary_rank = round(len(rows) * GROUP2_BOUNDARY_FRACTION)
    for r in rows:
        category, reason = categorize(r, stats, boundary_rank)
        r["category"] = category
        r["category_reason"] = reason
    return boundary_rank
