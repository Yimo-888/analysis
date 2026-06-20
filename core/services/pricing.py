"""
Cost-driven price-tier model (illustrative, invented numbers).

A SKU's per-ml cost maps to a price *tier*; each tier has a published price per
bottle size. The automation app's mispricing audit inverts this: given a
published price it infers the tier that was used, then compares it to the tier
the current cost implies.
"""
TIER_NAMES = [f"T{i}" for i in range(1, 11)]
TIER_MIN_COST_PER_ML = {
    "T1": 0.00, "T2": 0.40, "T3": 0.80, "T4": 1.30, "T5": 2.00,
    "T6": 3.00, "T7": 4.20, "T8": 5.60, "T9": 7.00, "T10": 9.00,
}
_TIER_PRICE_10ML = {
    "T1": 13.0, "T2": 16.0, "T3": 20.0, "T4": 25.0, "T5": 32.0,
    "T6": 42.0, "T7": 56.0, "T8": 74.0, "T9": 98.0, "T10": 130.0,
}
SIZES = ["5ml", "10ml", "32ml"]
SIZE_ML = {"5ml": 5, "10ml": 10, "32ml": 32}
_SIZE_FACTOR = {"5ml": 0.72, "10ml": 1.0, "32ml": 2.70}


def tier_index(tier):
    return TIER_NAMES.index(tier) if tier in TIER_NAMES else -1


def expected_tier(cost_per_ml):
    chosen = TIER_NAMES[0]
    for t in TIER_NAMES:
        if cost_per_ml >= TIER_MIN_COST_PER_ML[t]:
            chosen = t
        else:
            break
    return chosen


def price(tier, size):
    if tier not in _TIER_PRICE_10ML or size not in _SIZE_FACTOR:
        return 0.0
    return round(_TIER_PRICE_10ML[tier] * _SIZE_FACTOR[size], 2)


def unit_cost(cost_per_ml, size):
    return round(float(cost_per_ml) * SIZE_ML.get(size, 10), 2)
