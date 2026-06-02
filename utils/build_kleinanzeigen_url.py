"""
Build Kleinanzeigen filter URLs from structured parameters.

This is the reverse of utils/parse_kleinanzeigen_url.py — given typed filter
parameters, it constructs the full Kleinanzeigen search URL including the
filter segment with category-specific prefix keys.
"""

from urllib.parse import urlencode
from typing import Optional, List

from utils.filter_catalog import get_filter_prefix, get_category_id

BASE_URL = "https://www.kleinanzeigen.de"


def build_filter_url(
    *,
    category_slug: Optional[str] = None,
    category_id: Optional[int] = None,
    query: Optional[str] = None,
    location: Optional[str] = None,
    radius: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    brands: Optional[List[str]] = None,
    fuel: Optional[List[str]] = None,
    transmission: Optional[str] = None,
    car_type: Optional[List[str]] = None,
    mileage_from: Optional[int] = None,
    mileage_to: Optional[int] = None,
    art: Optional[str] = None,
    page: int = 1,
) -> str:
    """
    Build a full Kleinanzeigen search URL from structured filter parameters.

    Parameters match the /inserate query params:
      category_slug  — e.g. "s-autos", "s-wohnwagen-mobile"
      category_id    — numeric ID (auto-resolved from category_slug if omitted)
      query          — search keyword
      location       — location string for query-string filter
      radius         — search radius in km
      min_price      — minimum price (EUR)
      max_price      — maximum price (EUR)
      year_from      — minimum year (Erstzulassung)
      year_to        — maximum year (None = open-ended upper bound)
      brands         — list of brand names
      fuel           — list of fuel types
      transmission   — "automatik" or "manuell"
      car_type       — list of car types (e.g. "kombi", "suv")
      mileage_from   — minimum mileage in km
      mileage_to     — maximum mileage in km (None = open-ended upper bound)
      art            — article type (e.g. "wohnwagen")
      page           — page number (1 = omitted from URL)

    Returns a full URL string that can be passed to /inserate-by-url or
    used directly for scraping.
    """
    path_parts: list[str] = []

    # Resolve category
    prefix = None
    if category_slug:
        prefix = get_filter_prefix(category_slug)
        if category_id is None:
            category_id = get_category_id(category_slug)
        path_parts.append(category_slug)

    # ── Path segments between category and filter ──────────────────────────
    # Query keyword goes in the path for category URLs (but NOT as a
    # subcategory — subcategories like "klima", "volkswagen" are handled
    # by the filter segment, so we skip them in the path to keep URLs
    # clean and canonical).

    # ── Price segment ──────────────────────────────────────────────────────
    if min_price is not None or max_price is not None:
        min_str = str(min_price) if min_price is not None else ""
        max_str = str(max_price) if max_price is not None else ""
        path_parts.append(f"preis:{min_str}:{max_str}")

    # ── Page segment (only for page > 1, inserted before filter segment) ──
    has_filters = any([
        category_id is not None,
        year_from is not None,
        brands,
        fuel,
        transmission,
        car_type,
        mileage_from is not None,
        art,
    ])

    if page > 1:
        page_seg = f"seite:{page}" if has_filters else f"s-seite:{page}"
        path_parts.append(page_seg)

    # ── Filter segment ─────────────────────────────────────────────────────
    filter_parts: list[str] = []

    # Category ID
    if category_id is not None:
        filter_parts.append(f"k0c{category_id}")

    if prefix:
        # Year (Erstzulassung)
        if year_from is not None:
            if year_to is not None:
                filter_parts.append(f"{prefix}.ez_i:{year_from},{year_to}")
            else:
                # Trailing comma = open-ended upper bound
                filter_parts.append(f"{prefix}.ez_i:{year_from},")

        # Brands
        if brands:
            brand_list = [b.strip().lower() for b in brands if b.strip()]
            if brand_list:
                if len(brand_list) == 1:
                    filter_parts.append(f"{prefix}.marke_s:{brand_list[0]}")
                else:
                    filter_parts.append(f"{prefix}.marke_s:({','.join(brand_list)})")

        # Fuel
        if fuel:
            fuel_list = [f.strip().lower() for f in fuel if f.strip()]
            if fuel_list:
                if len(fuel_list) == 1:
                    filter_parts.append(f"{prefix}.fuel_s:{fuel_list[0]}")
                else:
                    filter_parts.append(f"{prefix}.fuel_s:({','.join(fuel_list)})")

        # Transmission
        if transmission:
            filter_parts.append(f"{prefix}.shift_s:{transmission.strip().lower()}")

        # Car type
        if car_type:
            ct_list = [c.strip().lower() for c in car_type if c.strip()]
            if ct_list:
                if len(ct_list) == 1:
                    filter_parts.append(f"{prefix}.typ_s:{ct_list[0]}")
                else:
                    filter_parts.append(f"{prefix}.typ_s:({','.join(ct_list)})")

        # Mileage (Kilometerstand)
        if mileage_from is not None:
            # Trailing comma = open-ended upper bound (up to mileage_from km)
            filter_parts.append(f"{prefix}.km_i:{mileage_from},")

        # Article type
        if art:
            filter_parts.append(f"{prefix}.art_s:{art.strip().lower()}")

    # Combine filter parts into filter segment
    if filter_parts:
        path_parts.append("+".join(filter_parts))

    # ── Assemble path ─────────────────────────────────────────────────────
    path = "/" + "/".join(path_parts) if path_parts else "/"

    # ── Query-string params ────────────────────────────────────────────────
    params: dict[str, str | int] = {}
    if not category_slug and query:
        # For generic searches (no category), keyword goes in query string
        params["keywords"] = query
    if location:
        params["locationStr"] = location
    if radius is not None:
        params["radius"] = str(radius)

    query_string = f"?{urlencode(params)}" if params else ""

    return BASE_URL + path + query_string
