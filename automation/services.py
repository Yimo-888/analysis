"""
automation — the listing fan-out.

The core idea of the listing automation: one base product becomes many marketplace
listings. A fixed matrix of (bottle type × size) variants is expanded for each base
product, each variant getting its own generated SKU and title.
"""
import re

# (bottle_type, size) — the variant grid every base product is exploded into.
VARIANT_GRID = [
    ("Vial", "1ml"), ("Vial", "2ml"), ("Vial", "3ml"),
    ("Vial", "5ml"), ("Vial", "10ml"), ("Vial", "32ml"),
    ("Atomizer", "5ml"), ("Atomizer", "10ml"),
]
VARIANTS_PER_PRODUCT = len(VARIANT_GRID)


def _base_label(product):
    """The base sku without its decant size suffix, e.g. 'Creed Aventus 1ml' → 'Creed Aventus'."""
    return re.sub(r"\s+\d+ml$", "", product.sku).strip() or product.sku


def variant_sku(base_label, bottle_type, size):
    return f"{base_label} {size} {'V' if bottle_type == 'Vial' else 'A'}"


def expand(product):
    """Yield the (variant_sku, bottle_type, size, title) tuples for one base product."""
    base = _base_label(product)
    for bottle_type, size in VARIANT_GRID:
        yield (
            variant_sku(base, bottle_type, size),
            bottle_type, size,
            f"{product.name} — {size} {bottle_type}",
        )
