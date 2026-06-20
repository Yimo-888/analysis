"""
automation — the DX pricing pipeline + mispricing audit.

The pipeline auto-prices every SKU off its per-ml cost (cost → tier → published
price per bottle size). The audit is the safety net: it reconstructs the tier a
SKU was *published* at and flags anything published far below the tier its cost
implies — the classic signature of a failed cost lookup defaulting to the cheapest
tier.
"""
from core.services import pricing

MISPRICE_TIER_GAP = 2      # published >= 2 tiers below expected = flagged
SEVERE_TIER_GAP = 4


def audit(m):
    """Return (published_price, mispriced, severity) for one row."""
    pub, exp = m["published_tier"], m["expected_tier"]
    published_price = pricing.price(pub, m["max_size"])
    gap = pricing.tier_index(exp) - pricing.tier_index(pub)
    if gap >= SEVERE_TIER_GAP:
        return published_price, True, "Severe (≥4 tiers under)"
    if gap >= MISPRICE_TIER_GAP:
        return published_price, True, "Likely mispriced"
    return published_price, False, ""


def enrich_pricing(rows):
    for r in rows:
        published_price, mispriced, severity = audit(r)
        r["published_price"] = published_price
        r["mispriced"] = mispriced
        r["mispricing_severity"] = severity
