"""
automation — the listing fan-out.

The core idea of the listing automation: one base product becomes many marketplace
listings. A fixed matrix of (variant type × pack size) is expanded for each base
product, each variant getting its own generated SKU and title.
"""
# (variant_type, size) — the grid every base product is exploded into.
VARIANT_GRID = [
    ("Single", "S"), ("Single", "M"), ("Single", "L"),
    ("Single", "XL"), ("Single", "2XL"), ("Single", "BULK"),
    ("Bundle", "M"), ("Bundle", "L"),
]
VARIANTS_PER_PRODUCT = len(VARIANT_GRID)

# the connected steps of the pipeline — used by the overview "how it works" flow
PIPELINE_STEPS = [
    ("Catalog", "read every active SKU"),
    ("Fan-out", f"× {VARIANTS_PER_PRODUCT} variants each"),
    ("Generate", "SKU · title · payload"),
    ("Post", "marketplace API (bulk)"),
    ("Track", "posted / pending / failed"),
]


def _code(variant_type):
    return "SI" if variant_type == "Single" else "BU"


def expand(product):
    """Yield the (variant_sku, variant_type, size, title) tuples for one base product."""
    for variant_type, size in VARIANT_GRID:
        yield (
            f"{product.sku}-{_code(variant_type)}-{size}",
            variant_type, size,
            f"{product.name} — {variant_type} {size}",
        )
