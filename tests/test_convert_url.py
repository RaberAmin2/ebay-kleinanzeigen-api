"""
Unit tests for POST /convert-url endpoint.

Run with:
  pytest tests/test_convert_url.py -v
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.convert_url import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def post(url: str) -> dict:
    resp = client.post("/convert-url", json={"url": url})
    assert resp.status_code == 200
    return resp.json()


# ── Basic category URL (no keyword, no price) ────────────────────────────────


def test_category_only():
    data = post(
        "https://www.kleinanzeigen.de/s-wohnwagen-mobile/wohnwagen/"
        "c220+wohnwagen_mobile.art_s:wohnwagen+wohnwagen_mobile.ez_i:2008%2C"
    )
    ip = data["inserate_params"]
    assert ip["page_count"] == 1
    assert "query" not in ip
    assert ip["category_slug"] == "s-wohnwagen-mobile"
    assert ip["category_id"] == 220
    assert ip["art"] == "wohnwagen"
    assert ip["year_from"] == 2008
    assert ip["year_to"] is None

    u = data["unmapped"]
    assert u["subcategory"] == "wohnwagen"


# ── Full URL: keyword, price range, brands, year ─────────────────────────────


def test_full_url():
    data = post(
        "https://www.kleinanzeigen.de/s-wohnwagen-mobile/wohnwagen/"
        "preis:1000:15000/klima/"
        "k0c220+wohnwagen_mobile.art_s:wohnwagen"
        "+wohnwagen_mobile.ez_i:2008%2C"
        "+wohnwagen_mobile.marke_s:(fendt%2Cknaus)"
    )
    ip = data["inserate_params"]
    assert ip["query"] == "klima"
    assert ip["min_price"] == 1000
    assert ip["max_price"] == 15000
    assert ip["page_count"] == 1
    assert ip["category_id"] == 220
    assert ip["art"] == "wohnwagen"
    assert ip["year_from"] == 2008
    assert ip["brands"] == "fendt,knaus"
    assert ip["category_slug"] == "s-wohnwagen-mobile"

    u = data["unmapped"]
    assert u["subcategory"] == "wohnwagen"


# ── Query-string keyword + location + radius ─────────────────────────────────


def test_querystring_params():
    data = post(
        "https://www.kleinanzeigen.de/s-anzeige:angebote"
        "?keywords=wohnwagen&locationStr=Berlin&radius=50"
    )
    ip = data["inserate_params"]
    assert ip["query"] == "wohnwagen"
    assert ip["location"] == "Berlin"
    assert ip["radius"] == 50


# ── Pagination ────────────────────────────────────────────────────────────────


def test_page_number():
    data = post(
        "https://www.kleinanzeigen.de/s-wohnwagen-mobile/wohnwagen/seite:3/c220"
    )
    assert data["inserate_params"]["page_count"] == 3


def test_s_seite_page():
    data = post("https://www.kleinanzeigen.de/s-wohnwagen-mobile/s-seite:4/c220")
    assert data["inserate_params"]["page_count"] == 4


# ── Single brand ─────────────────────────────────────────────────────────────


def test_single_brand():
    data = post(
        "https://www.kleinanzeigen.de/s-wohnwagen-mobile/wohnwagen/"
        "c220+wohnwagen_mobile.marke_s:fendt"
    )
    assert data["inserate_params"]["brands"] == "fendt"


# ── Missing / empty URL ───────────────────────────────────────────────────────


def test_empty_url_returns_defaults():
    data = post("")
    assert data["inserate_params"]["page_count"] == 1
    assert data["unmapped"] == {}


# ── Unmapped → now mapped keys ───────────────────────────────────────────────


def test_category_keys_now_in_inserate_params():
    """Category-level filter keys that were previously unmapped are now
    expressed via /inserate structured params."""
    data = post(
        "https://www.kleinanzeigen.de/s-wohnwagen-mobile/wohnwagen/"
        "c220+wohnwagen_mobile.art_s:wohnwagen"
    )
    ip = data["inserate_params"]
    # These are now mapped to /inserate params
    assert ip["category_slug"] == "s-wohnwagen-mobile"
    assert ip["category_id"] == 220
    assert ip["art"] == "wohnwagen"
    # The subcategory is kept in unmapped for now (used for path building)
    assert data["unmapped"]["subcategory"] == "wohnwagen"
    # Not present in this URL
    for key in ("brands", "year_from", "year_to", "fuel", "transmission", "car_type", "mileage_from"):
        assert ip.get(key) is None


# ── Autos URLs ────────────────────────────────────────────────────────────────


def test_autos_category_only():
    # "klima" lands at path position 1 → parsed as subcategory, not path_keyword
    data = post("https://www.kleinanzeigen.de/s-autos/klima/k0c216")
    ip = data["inserate_params"]
    assert "query" not in ip
    assert ip["page_count"] == 1
    assert ip["category_slug"] == "s-autos"
    assert ip["category_id"] == 216

    u = data["unmapped"]
    assert u["subcategory"] == "klima"


def test_autos_with_brand_and_keyword():
    data = post(
        "https://www.kleinanzeigen.de/s-autos/volkswagen/klima/"
        "k0c216+autos.marke_s:volkswagen"
    )
    ip = data["inserate_params"]
    assert ip["query"] == "klima"
    assert ip["page_count"] == 1
    assert ip["category_slug"] == "s-autos"
    assert ip["category_id"] == 216
    assert ip["brands"] == "volkswagen"

    u = data["unmapped"]
    assert u["subcategory"] == "volkswagen"


def test_autos_full_filters():
    data = post(
        "https://www.kleinanzeigen.de/s-autos/volkswagen/klima/"
        "k0c216+autos.ez_i:2008%2C+autos.fuel_s:lpg+autos.km_i:2%2C"
        "+autos.marke_s:volkswagen+autos.shift_s:automatik+autos.typ_s:(kombi%2Csuv)"
    )
    ip = data["inserate_params"]
    assert ip["query"] == "klima"
    assert ip["page_count"] == 1
    assert ip["category_slug"] == "s-autos"
    assert ip["category_id"] == 216
    assert ip["year_from"] == 2008
    assert ip["year_to"] is None
    assert ip["brands"] == "volkswagen"
    assert ip["fuel"] == "lpg"
    assert ip["transmission"] == "automatik"
    assert ip["car_type"] == "kombi,suv"
    assert ip["mileage_from"] == 2

    u = data["unmapped"]
    assert u["subcategory"] == "volkswagen"
    # No unknown_attrs left — all recognized filters are now mapped
    assert "unknown_attrs" not in u
