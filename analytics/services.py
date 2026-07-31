"""
analytics (v1) — the original, textbook design.

Classical inventory theory: weighted demand, safety stock, reorder point, EOQ,
inventory turnover, and a Pareto-optimal frontier over (sales, profit, ROI).
Elegant — and it reads demand off the *current* inventory snapshot, which is
exactly where it breaks (see the analytics2 rewrite).
"""
import math

from core.services.metrics import normalizer

# fixed objective weights (the v1 "house view")
W_SALES, W_PROFIT, W_ROI = 0.2, 0.5, 0.3
# classical inventory constants (illustrative)
LEAD_TIME_DAYS = 7
SERVICE_Z = 1.65          # ~95% service level
ORDER_COST = 50.0         # $ per purchase order
HOLDING_COST = 2.0        # $ per unit per year


def pareto_optimal_flags(points):
    """points: list of (sales_norm, profit_norm, roi_norm) → list[bool]."""
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


def _classical_metrics(r):
    """The textbook inventory metrics for one product row (computed in place)."""
    daily = r["weighted_daily_sales"]
    std = r["daily_std"]
    stock = r["current_inventory"]
    annual_demand = daily * 365

    safety = SERVICE_Z * std * math.sqrt(LEAD_TIME_DAYS)
    reorder = daily * LEAD_TIME_DAYS + safety
    eoq = math.sqrt(2 * annual_demand * ORDER_COST / HOLDING_COST) if annual_demand > 0 else 0
    doi = stock / daily if daily > 0 else 999
    turnover = 365 / doi if doi > 0 else 0
    suggested = max(round(reorder - stock), 0)
    growth = ((r["recent_avg"] - r["mid_avg"]) / r["mid_avg"] * 100) if r["mid_avg"] > 0 else 0.0

    r["safety_stock"] = int(round(safety))
    r["reorder_point"] = int(round(reorder))
    r["eoq"] = int(round(eoq))
    r["days_supply"] = int(min(doi, 999))
    r["days_of_inventory"] = int(min(doi, 999))
    r["inventory_turnover"] = round(turnover, 1)
    r["suggested_qty"] = suggested
    r["growth_rate_pct"] = round(growth, 1)
    r["profit_per_day"] = round(r["profit_total"] / max(r["days_with_sales"], 1), 2)
    r["roi_pct"] = round(r["roi"] * 100, 2)
    r["sell_through_pct"] = round(r["sell_through_rate"] * 100, 2)


def enrich_v1(rows):
    """Add all v1 fields to each row dict (in place)."""
    for r in rows:
        _classical_metrics(r)

    # normalized objectives (0..1) for the frontier + balanced score
    norm_sales = normalizer([r["weighted_daily_sales"] for r in rows])
    norm_profit = normalizer([r["profit_total"] for r in rows])
    norm_roi = normalizer([r["roi"] for r in rows])
    norm_str = normalizer([r["sell_through_rate"] for r in rows])
    norm_turn = normalizer([r["inventory_turnover"] for r in rows])
    for r in rows:
        r["sales_norm"] = round(norm_sales(r["weighted_daily_sales"]), 4)
        r["profit_norm"] = round(norm_profit(r["profit_total"]), 4)
        r["roi_norm"] = round(norm_roi(r["roi"]), 4)
        r["sell_through_norm"] = round(norm_str(r["sell_through_rate"]), 4)
        r["turnover_norm"] = round(norm_turn(r["inventory_turnover"]), 4)
        r["score_balanced"] = round(
            W_SALES * r["sales_norm"] + W_PROFIT * r["profit_norm"] + W_ROI * r["roi_norm"], 4)

    flags = pareto_optimal_flags([(r["sales_norm"], r["profit_norm"], r["roi_norm"]) for r in rows])
    for r, f in zip(rows, flags):
        r["is_pareto"] = f
        r["status"] = "Optimal" if f else "Optimize"
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


def _placeholder_profit(pid):
    """Deterministic, obviously-synthetic profit figure (no real dollar data).

    Returns a small integer in 1..20 keyed off the product id, so the demo never
    surfaces real-looking financials while staying stable and varied per SKU.
    """
    return (pid * 13) % 20 + 1


def build_product_stats(rows, ref_date):
    """Materialize rows into unsaved ProductStats instances."""
    from .models import ProductStats
    return [
        ProductStats(
            product_id=r["_pid"], run_date=ref_date,
            stock=r["current_inventory"], daily_sales=round(r["weighted_daily_sales"], 2),
            days_supply=r["days_supply"], total_profit=_placeholder_profit(r["_pid"]),
            roi_pct=r["roi_pct"], score=r["score_balanced"], is_pareto=r["is_pareto"],
            status=r["status"], profit_per_day=(r["_pid"] % 3) + 1,
            sell_through_pct=r["sell_through_pct"], reorder_point=r["reorder_point"],
            eoq=r["eoq"], safety_stock=r["safety_stock"], days_of_inventory=r["days_of_inventory"],
            growth_rate_pct=r["growth_rate_pct"], suggested_qty=r["suggested_qty"],
            inventory_turnover=r["inventory_turnover"],
            sales_norm=round(r["sales_norm"] * 100, 1), profit_norm=round(r["profit_norm"] * 100, 1),
            roi_norm=round(r["roi_norm"] * 100, 1), sell_through_norm=round(r["sell_through_norm"] * 100, 1),
            turnover_norm=round(r["turnover_norm"] * 100, 1),
        )
        for r in rows
    ]
