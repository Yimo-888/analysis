"""
Cost-driven price-tier model (illustrative, invented numbers).

A SKU's per-unit cost maps to a price *tier*; each tier has a published price per
pack size. This drives the ROI metric used in ranking and categorization
(margin = tier price − pack cost).
"""
TIER_NAMES = [f"T{i}" for i in range(1, 11)]
TIER_MIN_COST_PER_UNIT = {
    "T1": 0.00, "T2": 0.40, "T3": 0.80, "T4": 1.30, "T5": 2.00,
    "T6": 3.00, "T7": 4.20, "T8": 5.60, "T9": 7.00, "T10": 9.00,
}
# Base published price per tier (for the reference "2XL" pack); other sizes scale.
_TIER_BASE_PRICE = {
    "T1": 13.0, "T2": 16.0, "T3": 20.0, "T4": 25.0, "T5": 32.0,
    "T6": 42.0, "T7": 56.0, "T8": 74.0, "T9": 98.0, "T10": 130.0,
}
# Pack sizes — smaller packs cost more per unit, so price is far from linear in size.
SIZES = ["S", "M", "L", "XL", "2XL", "BULK"]
SIZE_UNITS = {"S": 1, "M": 2, "L": 3, "XL": 5, "2XL": 10, "BULK": 32}
_SIZE_FACTOR = {"S": 0.30, "M": 0.42, "L": 0.52, "XL": 0.72, "2XL": 1.0, "BULK": 2.70}


def tier_index(tier):
    return TIER_NAMES.index(tier) if tier in TIER_NAMES else -1


def expected_tier(cost_per_unit):
    chosen = TIER_NAMES[0]
    for t in TIER_NAMES:
        if cost_per_unit >= TIER_MIN_COST_PER_UNIT[t]:
            chosen = t
        else:
            break
    return chosen


def price(tier, size):
    if tier not in _TIER_BASE_PRICE or size not in _SIZE_FACTOR:
        return 0.0
    return round(_TIER_BASE_PRICE[tier] * _SIZE_FACTOR[size], 2)


def pack_cost(cost_per_unit, size):
    return round(float(cost_per_unit) * SIZE_UNITS.get(size, 1), 2)
