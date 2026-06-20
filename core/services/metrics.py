"""
Shared numeric helpers + base per-SKU metric computation.

Everything portfolio-relative (percentiles, ranks, categorization) lives in the
feature apps; this module only computes facts about a single SKU from its own
sales history, plus the small stats helpers everyone reuses.
"""
from datetime import timedelta

from . import pricing

WINDOW_DAYS = 365
# (label, start_day, end_day, weight) measured back from the reference date
SUBWINDOWS = (
    ("recent", 0, 60, 0.5),
    ("mid", 60, 180, 0.3),
    ("long", 180, 365, 0.2),
)


def median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def percentile(values, p):
    s = sorted(values)
    if not s:
        return 0.0
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def normalizer(values):
    lo, hi = min(values), max(values)
    span = hi - lo
    if span <= 0:
        return lambda v: 0.0
    return lambda v: (v - lo) / span


def interp_factor(value, breakpoints):
    """Piecewise-linear ramp over sorted (x, y) breakpoints."""
    if value <= breakpoints[0][0]:
        return breakpoints[0][1]
    if value >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for (x0, y0), (x1, y1) in zip(breakpoints, breakpoints[1:]):
        if x0 <= value <= x1:
            t = (value - x0) / (x1 - x0) if x1 != x0 else 0
            return y0 + (y1 - y0) * t
    return breakpoints[-1][1]


def compute_base_metrics(p, sales_by_day, ref_date):
    """Per-SKU facts. `p` is a dict of product attributes."""
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
    naive_sell_through = total_units / max(current_inv, 1)           # v1: vs current snapshot
    avg_inv = p["avg_window_inventory"]
    grounded_sell_through = (                                        # v2: vs average stock
        total_units / (avg_inv + total_units) if (avg_inv + total_units) > 0 else 0.0
    )
    days_of_inventory = current_inv / weighted_daily_sales if weighted_daily_sales > 0 else 999.0

    size = p["max_size"]
    cost_unit = pricing.unit_cost(p["cost_per_ml"], size)
    exp_tier = pricing.expected_tier(float(p["cost_per_ml"]))
    correct_price = pricing.price(exp_tier, size)
    profit_unit = correct_price - cost_unit
    roi = profit_unit / cost_unit if cost_unit > 0 else 0.0

    last_sale = max((d for d, u in sales_by_day.items() if u > 0), default=None)
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
        "profit_total": profit_unit * total_units,
        "inventory_value": round(current_inv * cost_unit, 2),
        "expected_tier": exp_tier,
        "current_inventory": current_inv,
        "days_since_sale": (ref_date - last_sale).days if last_sale else 9999,
        "liquid_age": liquid_age,
        "is_new": p["is_new"],
        "lab_qty": p["lab_qty"],
        "wh_qty": p["wh_qty"],
        "max_size": size,
    }
