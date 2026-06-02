"""
Unit tests for utils/build_kleinanzeigen_url.py.

Run with:
  pytest tests/test_build_url.py -v
"""

import pytest
from utils.build_kleinanzeigen_url import build_filter_url
from utils.parse_kleinanzeigen_url import parse_kleinanzeigen_url


# ── Basic cases ──────────────────────────────────────────────────────────────


def test_empty_returns_base():
    url = build_filter_url()
    assert url == "https://www.kleinanzeigen.de/"


def test_query_only():
    url = build_filter_url(query="wohnwagen")
    assert "keywords=wohnwagen" in url
    assert url == "https://www.kleinanzeigen.de/?keywords=wohnwagen"


def test_location_and_radius():
    url = build_filter_url(location="Berlin", radius=50)
    assert "locationStr=Berlin" in url
    assert "radius=50" in url


def test_price_range():
    url = build_filter_url(min_price=1000, max_price=15000)
    assert "/preis:1000:15000" in url


def test_price_min_only():
    url = build_filter_url(min_price=500)
    assert "/preis:500:" in url


def test_price_max_only():
    url = build_filter_url(max_price=20000)
    assert "/preis::20000" in url


# ── Category URLs ────────────────────────────────────────────────────────────


def test_category_slug_resolves_prefix():
    url = build_filter_url(category_slug="s-autos")
    assert "/s-autos/" in url
    assert "c216" in url


def test_category_wohnwagen():
    url = build_filter_url(category_slug="s-wohnwagen-mobile")
    assert "/s-wohnwagen-mobile/" in url
    assert "c220" in url


def test_category_with_query():
    url = build_filter_url(category_slug="s-autos", query="klima")
    assert "/s-autos/" in url
    assert "c216" in url
    # For category URLs, query does NOT go in query string
    assert "keywords" not in url


# ── Page numbers ─────────────────────────────────────────────────────────────


def test_page_1_omitted():
    url = build_filter_url(page=1)
    assert "seite" not in url
    assert "s-seite" not in url


def test_page_gt_1_generic():
    url = build_filter_url(page=3)
    assert "s-seite:3" in url


def test_page_gt_1_with_category():
    url = build_filter_url(category_slug="s-autos", page=3)
    assert "seite:3" in url
    assert "s-seite" not in url


# ── Year filter ──────────────────────────────────────────────────────────────


def test_year_from():
    url = build_filter_url(category_slug="s-autos", year_from=2008)
    assert "autos.ez_i:2008," in url


def test_year_range():
    url = build_filter_url(category_slug="s-autos", year_from=2008, year_to=2024)
    assert "autos.ez_i:2008,2024" in url


# ── Brands ───────────────────────────────────────────────────────────────────


def test_single_brand():
    url = build_filter_url(category_slug="s-autos", brands=["volkswagen"])
    assert "autos.marke_s:volkswagen" in url


def test_multiple_brands():
    url = build_filter_url(category_slug="s-autos", brands=["volkswagen", "audi"])
    assert "+autos.marke_s:(volkswagen,audi)" in url


# ── Fuel ─────────────────────────────────────────────────────────────────────


def test_single_fuel():
    url = build_filter_url(category_slug="s-autos", fuel=["lpg"])
    assert "autos.fuel_s:lpg" in url


def test_multiple_fuel():
    url = build_filter_url(category_slug="s-autos", fuel=["lpg", "cng"])
    assert "+autos.fuel_s:(lpg,cng)" in url


# ── Transmission ─────────────────────────────────────────────────────────────


def test_transmission():
    url = build_filter_url(category_slug="s-autos", transmission="automatik")
    assert "autos.shift_s:automatik" in url


# ── Car type ─────────────────────────────────────────────────────────────────


def test_single_car_type():
    url = build_filter_url(category_slug="s-autos", car_type=["kombi"])
    assert "autos.typ_s:kombi" in url


def test_multiple_car_types():
    url = build_filter_url(category_slug="s-autos", car_type=["kombi", "suv"])
    assert "+autos.typ_s:(kombi,suv)" in url


# ── Mileage ──────────────────────────────────────────────────────────────────


def test_mileage_from():
    url = build_filter_url(category_slug="s-autos", mileage_from=50000)
    assert "autos.km_i:50000," in url


# ── Article type ─────────────────────────────────────────────────────────────


def test_art():
    url = build_filter_url(category_slug="s-wohnwagen-mobile", art="wohnwagen")
    assert "wohnwagen_mobile.art_s:wohnwagen" in url


# ── Combined filters ─────────────────────────────────────────────────────────


def test_full_autos_filters():
    url = build_filter_url(
        category_slug="s-autos",
        year_from=2008,
        fuel=["lpg"],
        mileage_from=2,
        brands=["volkswagen"],
        transmission="automatik",
        car_type=["kombi", "suv"],
    )
    assert "/s-autos/" in url
    assert "c216" in url
    assert "autos.ez_i:2008," in url
    assert "autos.fuel_s:lpg" in url
    assert "autos.km_i:2," in url
    assert "autos.marke_s:volkswagen" in url
    assert "autos.shift_s:automatik" in url
    assert "autos.typ_s:(kombi,suv)" in url

    # Verify the filter segment is properly joined with +
    filter_idx = url.index("c216")
    filter_segment = url[filter_idx:]
    parts = filter_segment.split("+")
    assert len(parts) == 7  # c216 + 6 filters


# ── Round-trip tests (build → parse → compare) ──────────────────────────────


def test_roundtrip_autos_basic():
    original = build_filter_url(category_slug="s-autos")
    parsed = parse_kleinanzeigen_url(original)
    assert parsed["category_slug"] == "s-autos"
    assert parsed["category_id"] == 216


def test_roundtrip_autos_full():
    original = build_filter_url(
        category_slug="s-autos",
        year_from=2008,
        fuel=["lpg"],
        mileage_from=2,
        brands=["volkswagen"],
        transmission="automatik",
        car_type=["kombi", "suv"],
    )
    parsed = parse_kleinanzeigen_url(original)
    assert parsed["category_slug"] == "s-autos"
    assert parsed["category_id"] == 216
    assert parsed["year_from"] == 2008
    assert parsed["year_to"] is None
    assert parsed["brands"] == ["volkswagen"]
    assert parsed["fuel"] == ["lpg"]
    assert parsed["transmission"] == "automatik"
    assert parsed["car_type"] == ["kombi", "suv"]
    assert parsed["mileage_from"] == 2


def test_roundtrip_wohnwagen():
    original = build_filter_url(
        category_slug="s-wohnwagen-mobile",
        year_from=2008,
        art="wohnwagen",
        brands=["fendt", "knaus"],
    )
    parsed = parse_kleinanzeigen_url(original)
    assert parsed["category_slug"] == "s-wohnwagen-mobile"
    assert parsed["category_id"] == 220
    assert parsed["year_from"] == 2008
    assert parsed["art"] == "wohnwagen"
    assert sorted(parsed["brands"]) == ["fendt", "knaus"]


def test_roundtrip_no_filters_means_no_unknown_attrs():
    original = build_filter_url(category_slug="s-autos", year_from=2008,
                                fuel=["lpg"], transmission="automatik",
                                car_type=["kombi"], mileage_from=2,
                                brands=["volkswagen"])
    parsed = parse_kleinanzeigen_url(original)
    # All filters are recognized — no unknown_attrs
    assert "unknown_attrs" not in parsed


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_empty_brands_list_ignored():
    url = build_filter_url(category_slug="s-autos", brands=[])
    assert "marke_s" not in url


def test_brands_with_whitespace_stripped():
    url = build_filter_url(category_slug="s-autos", brands=[" volkswagen ", " audi "])
    assert "autos.marke_s:(volkswagen,audi)" in url


def test_fuel_with_empty_strings_ignored():
    url = build_filter_url(category_slug="s-autos", fuel=["lpg", "", "cng"])
    assert "+autos.fuel_s:(lpg,cng)" in url
