"""
Utility for parsing Kleinanzeigen URLs and mapping them to /inserate API params.
"""

import re
from urllib.parse import urlparse, parse_qs, unquote


def parse_kleinanzeigen_url(url: str) -> dict:
    """Parse a Kleinanzeigen URL and extract all known parameters."""
    parsed = urlparse(url)
    path = unquote(parsed.path).strip("/")
    qs = parse_qs(parsed.query)

    result = {}

    # ── Query-string params ───────────────────────────────────────────────
    if "keywords" in qs:
        result["query"] = qs["keywords"][0]
    if "locationStr" in qs:
        result["location"] = qs["locationStr"][0]
    if "radius" in qs:
        result["radius"] = int(qs["radius"][0])

    # ── Path segments ─────────────────────────────────────────────────────
    segments = path.split("/")
    filter_segment = None

    for i, seg in enumerate(segments):
        # Page — seite:2
        if seg.startswith("seite:"):
            result["page"] = int(seg.split(":")[1])

        # Page (generic search) — s-seite:2
        elif re.match(r"^s-seite:\d+$", seg):
            result["page"] = int(seg.split(":")[1])

        # Category slug — s-wohnwagen-mobile
        elif seg.startswith("s-") and "category_slug" not in result:
            result["category_slug"] = seg

        # Price range — preis:1000:15000
        elif seg.startswith("preis:"):
            parts = seg.split(":")
            if len(parts) >= 3:
                if parts[1]:
                    result["min_price"] = int(parts[1])
                if parts[2]:
                    result["max_price"] = int(parts[2])

        # Filter segment — c220+... or k0c220+...
        elif re.match(r"^k?\d*c\d+", seg):
            filter_segment = seg

        # Subcategory — second segment
        elif i == 1:
            result["subcategory"] = seg

        # Path keyword — between subcategory and filter segment
        elif filter_segment is None and i > 1:
            result["path_keyword"] = seg

    # ── Filter segment ────────────────────────────────────────────────────
    if filter_segment:
        fs = filter_segment[2:] if filter_segment.startswith("k0") else filter_segment

        for attr in fs.split("+"):
            # Category ID — c220
            if re.match(r"^c\d+$", attr):
                result["category_id"] = int(attr[1:])
                continue

            if ":" not in attr:
                continue

            key, value = attr.split(":", 1)

            # Year — *.ez_i:2008,  (trailing comma = open-ended)
            if key.endswith(".ez_i"):
                year_str = value.rstrip(",")
                if year_str:
                    result["year_from"] = int(year_str)
                if value.endswith(","):
                    result["year_to"] = None

            # Article type — *.art_s:wohnwagen
            elif key.endswith(".art_s"):
                result["art"] = value

            # Brands — *.marke_s:(fendt,knaus) or *.marke_s:fendt
            elif key.endswith(".marke_s"):
                if value.startswith("(") and value.endswith(")"):
                    result["brands"] = value[1:-1].split(",")
                else:
                    result["brands"] = [value]

            # Unknown attributes — keep for transparency
            else:
                result.setdefault("unknown_attrs", {})[key] = value

    # ── Post-process unknown_attrs into known keys ─────────────────────────
    _promote_known_attrs(result)

    return result


def _promote_known_attrs(result: dict) -> None:
    """Move known filter attributes from unknown_attrs into top-level keys."""
    ua = result.get("unknown_attrs", {})
    if not ua:
        return

    for key, value in list(ua.items()):
        # Fuel — autos.fuel_s:lpg or autos.fuel_s:(cng,lpg)
        if key.endswith(".fuel_s"):
            if value.startswith("(") and value.endswith(")"):
                result["fuel"] = value[1:-1].split(",")
            else:
                result["fuel"] = [value]
            del ua[key]

        # Transmission — autos.shift_s:automatik
        elif key.endswith(".shift_s"):
            result["transmission"] = value
            del ua[key]

        # Car type — autos.typ_s:(kombi,suv) or autos.typ_s:kombi
        elif key.endswith(".typ_s"):
            if value.startswith("(") and value.endswith(")"):
                result["car_type"] = value[1:-1].split(",")
            else:
                result["car_type"] = [value]
            del ua[key]

        # Mileage — autos.km_i:2, (trailing comma = open-ended)
        elif key.endswith(".km_i"):
            km_str = value.rstrip(",")
            if km_str:
                result["mileage_from"] = int(km_str)
            del ua[key]

    # Clean up empty unknown_attrs
    if not ua:
        result.pop("unknown_attrs", None)


# Keys that map directly or indirectly to /inserate params
_MAPPED_SOURCE_KEYS = {
    "query",
    "path_keyword",
    "location",
    "radius",
    "min_price",
    "max_price",
    "page",
    # Category-level filters now supported by /inserate
    "category_slug",
    "category_id",
    "art",
    "year_from",
    "year_to",
    "brands",
    "fuel",
    "transmission",
    "car_type",
    "mileage_from",
    # Note: "subcategory" is intentionally NOT listed here — it stays in
    # unmapped because /inserate has no subcategory param (the category
    # slug + filter segment fully specify the category scope).
}


def map_to_inserate_params(parsed: dict) -> tuple[dict, dict]:
    """
    Map parsed URL params to /inserate API params.

    Returns:
        inserate_params: only keys the current /inserate endpoint understands
        unmapped:        everything that could not be expressed via /inserate yet
    """
    inserate_params = {}

    # query: prefer explicit QS keyword, fall back to path keyword
    if "query" in parsed:
        inserate_params["query"] = parsed["query"]
    elif "path_keyword" in parsed:
        inserate_params["query"] = parsed["path_keyword"]

    for key in ("location", "radius", "min_price", "max_price"):
        if key in parsed:
            inserate_params[key] = parsed[key]

    inserate_params["page_count"] = parsed.get("page", 1)

    # ── Category-level filters ────────────────────────────────────────────
    for key in (
        "category_slug", "category_id",
        "year_from", "year_to",
        "art", "transmission", "mileage_from",
    ):
        if key in parsed:
            inserate_params[key] = parsed[key]

    # list-type params: join with comma for query-string representation
    for key in ("brands", "fuel", "car_type"):
        if key in parsed:
            inserate_params[key] = ",".join(parsed[key])

    unmapped = {k: v for k, v in parsed.items() if k not in _MAPPED_SOURCE_KEYS}

    return inserate_params, unmapped
