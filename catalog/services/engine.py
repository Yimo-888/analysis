"""
Catalyst analytics engine.

This is a clean reimplementation of the design ideas behind a production
inventory-analytics / lifecycle / dynamic-pricing system, written from scratch
for this demo over synthetic data. Two "generations" are computed side by side:

  v1  — the original, textbook design: normalize sales / profit / ROI, find the
        Pareto-optimal frontier, score on a fixed weighting. Elegant, but it
        reads demand off the *current* inventory snapshot, so an out-of-stock
        SKU with a little stale history looks like a star (phantom sell-through).

  v2  — the production design: ground sell-through in *average* inventory over
        the window, then run an explicit category cascade that, among other
        things, routes out-of-stock / genuinely-slow items away from "reorder".
        This is the version worth shipping.

The functions are deliberately pure (lists/dicts in, dicts out) so they are
easy to unit-test; `run_engine()` is the only part that touches the database.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import pricing

# ── Tunable constants (illustrative, not tuned to any real catalog) ──────────
WINDOW_DAYS = 365
SUBWINDOWS = (  # (label, start_day, end_day, weight) measured back from ref date
    ("recent", 0, 60, 0.5),
    ("mid", 60, 180, 0.3),
    ("long", 180, 365, 0.2),
)
GROUP2_BOUNDARY_FRACTION = 0.65   # rank below this fraction of the catalog = "challenged"
NEW_GRACE_DAYS = 60
LIQUIDATE_LIQUID_AGE = 365         # aging lab liquid starts clearing
DISPOSE_LIQUID_AGE = 540           # spoiled — write off
MISPRICE_TIER_GAP = 2              # published >= 2 tiers below expected = flagged

CATEGORY_COLORS = {  # used by the templates
    "New High Performer": "primary",
    "High-Demand Rare Item": "success",
    "Core Portfolio": "info",
    "Standard": "secondary",
    "Slow Mover": "warning",
    "Slow Mover/Watch": "warning",
    "Liquidate Candidate": "danger",
    "Dispose Candidate": "dark",
}
TIER_COLORS = {
    "NEW": "primary", "STAR": "success", "CORE": "info",
    "WATCH": "warning", "LIQUIDATE": "danger", "DISPOSE": "dark",
}


# ── Small numeric helpers (pure Python, no numpy needed) ─────────────────────
def median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def percentile(values, p):
    """Linear-interpolation percentile (p in 0..100)."""
    s = sorted(values)
    if not s:
        return 0.0
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _normalizer(values):
    lo, hi = min(values), max(values)
    span = hi - lo
    if span <= 0:
        return lambda v: 0.0
    return lambda v: (v - lo) / span


def interp_factor(value, breakpoints):
    """Piecewise-linear ramp. breakpoints: sorted list of (x, y). Below the
    first x → first y; above the last → last y; else linearly interpolated."""
    if value <= breakpoints[0][0]:
        return breakpoints[0][1]
    if value >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for (x0, y0), (x1, y1) in zip(breakpoints, breakpoints[1:]):
        if x0 <= value <= x1:
            t = (value - x0) / (x1 - x0) if x1 != x0 else 0
            return y0 + (y1 - y0) * t
    return breakpoints[-1][1]


# ── Per-SKU raw metrics ──────────────────────────────────────────────────────
def compute_raw_metrics(p, sales_by_day, ref_date):
    """
    p             : dict of product attributes
    sales_by_day  : dict {date: units}
    ref_date      : reference date (window ends here)
    """
    window_start = ref_date - timedelta(days=WINDOW_DAYS)
    total_units = 0
    days_with_sales = 0
    sub_totals = {label: 0 for label, *_ in SUBWINDOWS}

    for d, units in sales_by_day.items():
        if units <= 0 or d <= window_start or d > ref_date:
            continue
        total_units += units
        days_with_sales += 1
        age = (ref_date - d).days
        for label, start, end, _w in SUBWINDOWS:
            if start <= age < end:
                sub_totals[label] += units
                break

    weighted_daily_sales = 0.0
    for label, start, end, w in SUBWINDOWS:
        days = end - start
        weighted_daily_sales += w * (sub_totals[label] / days if days else 0)

    velocity = total_units / days_with_sales if days_with_sales else 0.0

    current_inv = p["current_inventory"]
    # v1: demand vs the *current* snapshot — explodes when stock is near zero.
    naive_sell_through = total_units / max(current_inv, 1)
    # v2: demand vs *average* stock held over the window — bounded, honest.
    avg_inv = p["avg_window_inventory"]
    grounded_sell_through = (
        total_units / (avg_inv + total_units) if (avg_inv + total_units) > 0 else 0.0
    )

    days_of_inventory = current_inv / weighted_daily_sales if weighted_daily_sales > 0 else 999.0

    size = p["max_size"]
    cost_unit = pricing.unit_cost(p["cost_per_ml"], size)
    exp_tier = pricing.expected_tier(float(p["cost_per_ml"]))
    correct_price = pricing.price(exp_tier, size)
    profit_unit = correct_price - cost_unit
    roi = profit_unit / cost_unit if cost_unit > 0 else 0.0
    profit_total = profit_unit * total_units
    inventory_value = current_inv * cost_unit

    last_sale = max((d for d, u in sales_by_day.items() if u > 0), default=None)
    days_since_sale = (ref_date - last_sale).days if last_sale else 9999

    liquid_age = (ref_date - p["liquid_opened_date"]).days if p.get("liquid_opened_date") else None

    return {
        "sku": p["sku"],
        "total_units": total_units,
        "weighted_daily_sales": round(weighted_daily_sales, 4),
        "velocity": round(velocity, 3),
        "naive_sell_through": round(naive_sell_through, 4),
        "sell_through_rate": round(grounded_sell_through, 4),
        "days_of_inventory": round(days_of_inventory, 1),
        "roi": round(roi, 4),
        "profit_total": profit_total,
        "inventory_value": round(inventory_value, 2),
        "expected_tier": exp_tier,
        "correct_price": correct_price,
        "current_inventory": current_inv,
        "days_since_sale": days_since_sale,
        "liquid_age": liquid_age,
        "is_new": p["is_new"],
        "lab_qty": p["lab_qty"],
        "wh_qty": p["wh_qty"],
        "max_size": size,
        "published_tier": p.get("published_tier") or exp_tier,
    }


# ── Categorization cascade (v2) ──────────────────────────────────────────────
def categorize(m, stats, boundary_rank):
    """Return (category, reason). `m` includes 'portfolio_rank'."""
    rank = m["portfolio_rank"]

    if rank > boundary_rank:
        if m["inventory_value"] > stats["inv_value_p65"]:
            return "Liquidate Candidate", (
                f"Challenged (rank {rank} > {boundary_rank}) with high capital at "
                f"risk (${m['inventory_value']:,.0f} > p65) — clear it down."
            )
        return "Dispose Candidate", (
            f"Challenged (rank {rank} > {boundary_rank}) with little capital at "
            f"risk — write off rather than discount."
        )

    if m["is_new"] and m["portfolio_score"] > stats["score_median"]:
        return "New High Performer", "New SKU already above median — protect from demotion."

    if m["current_inventory"] <= 0 and m["days_since_sale"] > 30:
        return "Slow Mover/Watch", (
            f"Out of stock and no sale in {m['days_since_sale']}d — freeze purchasing, "
            f"don't liquidate (it may just be temporarily OOS)."
        )

    if m["sell_through_rate"] > stats["str_p75"] and m["roi"] > stats["roi_median"]:
        return "High-Demand Rare Item", (
            "Top-quartile sell-through and above-median ROI — sells fast at a good margin."
        )

    if m["is_pareto"]:
        return "Core Portfolio", "On the sales/profit/ROI efficient frontier — a portfolio anchor."

    if (m["current_inventory"] > 0
            and m["sell_through_rate"] < stats["str_p25"]
            and m["weighted_daily_sales"] < stats["wds_median"]):
        return "Slow Mover", (
            "In stock but bottom-quartile sell-through and below-median velocity — "
            "freeze purchasing, keep selling at full price."
        )

    return "Standard", "Solid mid-catalog performer."


# ── Lifecycle routing + discount ─────────────────────────────────────────────
def resolve_lifecycle(category, m):
    """Map a category to a lifecycle tier, choosing a liquidation strategy from
    where the inventory physically sits. Returns (tier, strategy)."""
    simple = {
        "New High Performer": ("NEW", ""),
        "High-Demand Rare Item": ("STAR", ""),
        "Core Portfolio": ("CORE", ""),
        "Standard": ("CORE", ""),
        "Slow Mover": ("WATCH", ""),
        "Slow Mover/Watch": ("WATCH", ""),
    }
    if category in simple:
        return simple[category]

    age = m["liquid_age"]
    lab, wh = m["lab_qty"], m["wh_qty"]

    if category == "Liquidate Candidate":
        if lab > 0 and age is not None and age > LIQUIDATE_LIQUID_AGE:
            return "LIQUIDATE", "WEBSITE_DISCOUNT"
        if lab > 0:
            return "WATCH", ""          # fresh liquid — hold at full price
        if wh > 0:
            return "LIQUIDATE", "EBAY"  # sealed only — move on the marketplace
        return "WATCH", ""              # nothing physical — just monitor

    # Dispose Candidate
    if lab > 0 and age is not None and age > DISPOSE_LIQUID_AGE:
        return "DISPOSE", ""            # spoiled
    if wh > 0:
        return "LIQUIDATE", "EBAY"      # rescue sealed stock before writing off
    if lab > 0:
        return "LIQUIDATE", "WEBSITE_DISCOUNT"
    return "DISPOSE", ""


def discount_for(m, boundary_rank, catalog_size):
    """Multi-factor clearance discount (%) for website liquidation strategies.
    Weights rank, liquid age, and overstock; clamped to a sane band."""
    rank_ratio = m["portfolio_rank"] / max(catalog_size, 1)
    rank_f = interp_factor(rank_ratio, [(0.60, 0), (0.75, 10), (0.90, 20), (1.0, 30)])
    age_f = interp_factor(m["liquid_age"] or 0, [(120, 0), (240, 10), (365, 20), (480, 30)])
    over_f = interp_factor(m["days_of_inventory"], [(120, 0), (240, 10), (480, 20), (720, 30)])
    raw = 10 + 0.30 * rank_f + 0.30 * age_f + 0.40 * over_f
    return int(round(max(5, min(40, raw))))


# ── Pareto frontier (v1) ─────────────────────────────────────────────────────
def pareto_optimal_flags(points):
    """points: list of (sales_norm, profit_norm, roi_norm). Returns list[bool].
    A point is Pareto-optimal if no other point is >= in all three objectives
    and strictly greater in at least one."""
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


# ── Orchestration over the database ──────────────────────────────────────────
def run_engine(run_date=None):
    """Compute v1 + v2 metrics for every product and (re)write AnalyticsResult.
    Returns a small summary dict. This is the only DB-touching function."""
    from django.db import transaction

    from catalog.models import AnalyticsResult, DailySale, Product

    products = list(Product.objects.all())
    if not products:
        return {"products": 0}

    # 1 query for all sales, grouped in Python (keeps it O(queries)=O(1) at scale).
    sales_index = {}
    for s in DailySale.objects.all().values_list("product_id", "date", "units"):
        sales_index.setdefault(s[0], {})[s[1]] = s[2]

    ref_date = run_date or _max_sale_date(sales_index) or date.today()

    rows = []
    for p in products:
        pdict = {
            "sku": p.sku, "current_inventory": p.current_inventory,
            "avg_window_inventory": p.avg_window_inventory, "cost_per_ml": p.cost_per_ml,
            "max_size": p.max_size, "published_tier": p.published_tier,
            "lab_qty": p.lab_qty, "wh_qty": p.wh_qty, "is_new": p.is_new,
            "liquid_opened_date": p.liquid_opened_date,
        }
        m = compute_raw_metrics(pdict, sales_index.get(p.id, {}), ref_date)
        m["_pid"] = p.id
        rows.append(m)

    # ── Portfolio-wide statistics ──
    stats = {
        "roi_median": median([r["roi"] for r in rows]),
        "str_p75": percentile([r["sell_through_rate"] for r in rows], 75),
        "str_p25": percentile([r["sell_through_rate"] for r in rows], 25),
        "wds_median": median([r["weighted_daily_sales"] for r in rows]),
        "inv_value_p65": percentile([r["inventory_value"] for r in rows], 65),
    }

    # ── v2 portfolio score + rank ──
    norm_wds = _normalizer([r["weighted_daily_sales"] for r in rows])
    norm_str = _normalizer([r["sell_through_rate"] for r in rows])
    norm_roi = _normalizer([r["roi"] for r in rows])
    for r in rows:
        r["portfolio_score"] = round(
            0.40 * norm_wds(r["weighted_daily_sales"])
            + 0.30 * norm_str(r["sell_through_rate"])
            + 0.30 * norm_roi(r["roi"]),
            4,
        )
    rows.sort(key=lambda r: r["portfolio_score"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["portfolio_rank"] = i
    stats["score_median"] = median([r["portfolio_score"] for r in rows])

    # ── v1 normalized objectives, Pareto frontier, balanced score ──
    v1_sales = _normalizer([r["weighted_daily_sales"] for r in rows])
    v1_profit = _normalizer([r["profit_total"] for r in rows])
    v1_roi = _normalizer([r["roi"] for r in rows])
    for r in rows:
        r["sales_norm"] = round(v1_sales(r["weighted_daily_sales"]), 4)
        r["profit_norm"] = round(v1_profit(r["profit_total"]), 4)
        r["roi_norm"] = round(v1_roi(r["roi"]), 4)
        r["score_balanced"] = round(
            0.2 * r["sales_norm"] + 0.5 * r["profit_norm"] + 0.3 * r["roi_norm"], 4
        )
    flags = pareto_optimal_flags([(r["sales_norm"], r["profit_norm"], r["roi_norm"]) for r in rows])
    for r, f in zip(rows, flags):
        r["is_pareto"] = f
    by_v1 = sorted(rows, key=lambda r: r["score_balanced"], reverse=True)
    for i, r in enumerate(by_v1, start=1):
        r["v1_rank"] = i

    boundary_rank = round(len(rows) * GROUP2_BOUNDARY_FRACTION)
    catalog_size = len(rows)

    # ── Categorize, route lifecycle, price-audit ──
    for r in rows:
        category, reason = categorize(r, stats, boundary_rank)
        r["category"] = category
        r["category_reason"] = reason
        tier, strategy = resolve_lifecycle(category, r)
        r["lifecycle_tier"] = tier
        r["liquidation_strategy"] = strategy
        r["discount_pct"] = discount_for(r, boundary_rank, catalog_size) if strategy in {
            "WEBSITE_DISCOUNT", "BOTH"} else 0
        # v1's verdict for the same SKU (what the original design would have said)
        if r["is_pareto"]:
            r["v1_verdict"] = "Pareto-optimal — prioritize"
        elif r["v1_rank"] <= 0.40 * catalog_size:
            r["v1_verdict"] = "Healthy — reorder"
        else:
            r["v1_verdict"] = "Needs optimization"
        _audit_price(r)

    # ── Persist ──
    with transaction.atomic():
        AnalyticsResult.objects.all().delete()
        AnalyticsResult.objects.bulk_create([
            AnalyticsResult(
                product_id=r["_pid"], run_date=ref_date,
                weighted_daily_sales=r["weighted_daily_sales"],
                sell_through_rate=r["sell_through_rate"], velocity=r["velocity"],
                days_of_inventory=r["days_of_inventory"], roi=r["roi"],
                inventory_value=r["inventory_value"], portfolio_score=r["portfolio_score"],
                portfolio_rank=r["portfolio_rank"], category=r["category"],
                category_reason=r["category_reason"], lifecycle_tier=r["lifecycle_tier"],
                liquidation_strategy=r["liquidation_strategy"], discount_pct=r["discount_pct"],
                liquid_age_days=r["liquid_age"], naive_sell_through=r["naive_sell_through"],
                sales_norm=r["sales_norm"], profit_norm=r["profit_norm"],
                roi_norm=r["roi_norm"], score_balanced=r["score_balanced"],
                is_pareto_optimal=r["is_pareto"], v1_rank=r["v1_rank"],
                v1_verdict=r["v1_verdict"], expected_tier=r["expected_tier"],
                published_price=r["published_price"], correct_price=r["correct_price"],
                mispriced=r["mispriced"], mispricing_severity=r["mispricing_severity"],
            )
            for r in rows
        ], batch_size=500)

    return {
        "products": len(rows),
        "run_date": ref_date,
        "boundary_rank": boundary_rank,
        "mispriced": sum(1 for r in rows if r["mispriced"]),
    }


def _audit_price(r):
    """Compare the published tier to the cost-implied tier."""
    pub, exp = r["published_tier"], r["expected_tier"]
    r["published_price"] = pricing.price(pub, r["max_size"])
    gap = pricing.tier_index(exp) - pricing.tier_index(pub)
    if gap >= max(MISPRICE_TIER_GAP, 4):
        r["mispriced"], r["mispricing_severity"] = True, "Severe (≥4 tiers under)"
    elif gap >= MISPRICE_TIER_GAP:
        r["mispriced"], r["mispricing_severity"] = True, "Likely mispriced"
    else:
        r["mispriced"], r["mispricing_severity"] = False, ""


def _max_sale_date(sales_index):
    best = None
    for by_day in sales_index.values():
        for d in by_day:
            if best is None or d > best:
                best = d
    return best
