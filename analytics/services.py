"""
analytics (v1) — the original, textbook design.

Normalize sales / profit / ROI, find the Pareto-optimal frontier, and score on a
fixed weighting. Elegant, and it reads demand off the *current* inventory
snapshot — which is exactly where it breaks (see the dx_analytics rewrite).
"""
from core.services.metrics import normalizer

# fixed, hand-chosen objective weights (the v1 "house view")
W_SALES, W_PROFIT, W_ROI = 0.2, 0.5, 0.3


def pareto_optimal_flags(points):
    """points: list of (sales_norm, profit_norm, roi_norm) → list[bool].
    A point is optimal if no other point is >= on all axes and > on at least one."""
    n = len(points)
    flags = [True] * n
    for i in range(n):
        si, pi, ri = points[i]
        for j in range(n):
            if i == j:
                continue
            sj, pj, rj = points[j]
            if sj >= si and pj >= pi and rj >= ri and (sj > si or pj > pi or rj > ri):
                flags[i] = False
                break
    return flags


def enrich_v1(rows):
    """Add v1 fields to each row dict (in place)."""
    norm_sales = normalizer([r["weighted_daily_sales"] for r in rows])
    norm_profit = normalizer([r["profit_total"] for r in rows])
    norm_roi = normalizer([r["roi"] for r in rows])
    for r in rows:
        r["sales_norm"] = round(norm_sales(r["weighted_daily_sales"]), 4)
        r["profit_norm"] = round(norm_profit(r["profit_total"]), 4)
        r["roi_norm"] = round(norm_roi(r["roi"]), 4)
        r["score_balanced"] = round(
            W_SALES * r["sales_norm"] + W_PROFIT * r["profit_norm"] + W_ROI * r["roi_norm"], 4
        )
    flags = pareto_optimal_flags([(r["sales_norm"], r["profit_norm"], r["roi_norm"]) for r in rows])
    for r, f in zip(rows, flags):
        r["is_pareto"] = f
    for i, r in enumerate(sorted(rows, key=lambda r: r["score_balanced"], reverse=True), start=1):
        r["v1_rank"] = i
    cutoff = 0.40 * len(rows)
    for r in rows:
        if r["is_pareto"]:
            r["v1_verdict"] = "Pareto-optimal — prioritize"
        elif r["v1_rank"] <= cutoff:
            r["v1_verdict"] = "Healthy — reorder"
        else:
            r["v1_verdict"] = "Needs optimization"
