"""
Category → filter-prefix mappings and known value enumerations
for Kleinanzeigen structured filter URLs.

Add new categories and their allowed filter values here as they are discovered.
"""

from typing import Optional

# ── Category slug → filter prefix ──────────────────────────────────────────
# The filter prefix is used in filter-segment keys like {prefix}.ez_i, {prefix}.marke_s, etc.
CATEGORY_PREFIX: dict[str, str] = {
    "s-autos": "autos",
    "s-wohnwagen-mobile": "wohnwagen_mobile",
}

# ── Category slug → category ID ────────────────────────────────────────────
CATEGORY_IDS: dict[str, int] = {
    "s-autos": 216,
    "s-wohnwagen-mobile": 220,
}

# ── Known filter values per category ────────────────────────────────────────
# These are for documentation/validation; the URL builder does not enforce them.

FUEL_VALUES: set[str] = {
    "benzin", "diesel", "lpg", "cng", "elektro",
    "hybrid", "ethanol", "wasserstoff", "sonstige",
}

TRANSMISSION_VALUES: set[str] = {
    "automatik", "manuell", "halbautomatik",
}

CAR_TYPE_VALUES: set[str] = {
    "kombi", "suv", "limousine", "cabrio", "coupe",
    "kleinwagen", "van", "pickup", "sportwagen",
    "gewerblich", "wohnmobil",
}

# ── Subcategories (path keywords) per category ──────────────────────────────
# These appear between the category slug and the filter segment in the URL path.
SUBCATEGORIES: dict[str, set[str]] = {
    "s-autos": {"klima", "schaltung", "navi", "esp", "anhängerkupplung",
                "sitzheizung", "parkassistent", "tempomat", "led",
                "volkswagen", "audi", "bmw", "mercedes", "opel", "ford",
                "skoda", "seat", "toyota", "hyundai", "kia", "renault"},
    "s-wohnwagen-mobile": {"wohnwagen", "wohnmobil"},
}


def get_filter_prefix(category_slug: str) -> Optional[str]:
    """Return the filter-key prefix for a given category slug, or None if unknown."""
    return CATEGORY_PREFIX.get(category_slug)


def get_category_id(category_slug: str) -> Optional[int]:
    """Return the numeric category ID for a given category slug, or None if unknown."""
    return CATEGORY_IDS.get(category_slug)
