"""
Ultra-optimized router for maximum performance scraping.
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Query, Request, HTTPException
from scrapers.inserate_ultra_optimized import ultra_optimized_scrape_inserate

router = APIRouter()


@router.get("/inserate")
async def get_inserate_ultra_optimized(
    request: Request,
    query: str = Query(None, description="Search query string"),
    location: str = Query(None, description="Location filter"),
    radius: int = Query(None, description="Search radius in kilometers"),
    min_price: int = Query(None, description="Minimum price filter"),
    max_price: int = Query(None, description="Maximum price filter"),
    page_count: int = Query(1, ge=1, le=20, description="Number of pages to fetch"),
    min_publish_date: Optional[datetime] = Query(
        None,
        description="Stop fetching once listings published before this datetime (inclusive, format: YYYY-MM-DDTHH:MM:SS)",
    ),
    # ── Structured category-level filters ──────────────────────────────────
    category_slug: Optional[str] = Query(
        None,
        description="Category slug, e.g. 's-autos', 's-wohnwagen-mobile'",
    ),
    category_id: Optional[int] = Query(
        None,
        description="Numeric category ID (auto-resolved from category_slug if omitted)",
    ),
    year_from: Optional[int] = Query(
        None, description="Minimum year of manufacture (Erstzulassung)"
    ),
    year_to: Optional[int] = Query(
        None, description="Maximum year of manufacture (None = open-ended)"
    ),
    brands: Optional[str] = Query(
        None, description="Comma-separated brand names, e.g. 'volkswagen,audi'"
    ),
    fuel: Optional[str] = Query(
        None, description="Comma-separated fuel types, e.g. 'lpg,cng'"
    ),
    transmission: Optional[str] = Query(
        None, description="Transmission type: 'automatik' or 'manuell'"
    ),
    car_type: Optional[str] = Query(
        None, description="Comma-separated car types, e.g. 'kombi,suv'"
    ),
    mileage_from: Optional[int] = Query(
        None, description="Maximum mileage in km (open-ended upper bound)"
    ),
    art: Optional[str] = Query(
        None, description="Article type, e.g. 'wohnwagen'"
    ),
):
    """
    Fetch listings based on search criteria.

    Retrieves listings from Kleinanzeigen with support for various filters
    including location, price range, search terms, and category-level filters
    (year, brand, fuel, transmission, car type, mileage, article type).

    Category-level filters are only applied when category_slug is provided.
    Use /inserate-by-url for advanced filters not yet covered by structured params.
    """
    browser_manager = request.app.state.browser_manager
    if not browser_manager:
        raise HTTPException(status_code=503, detail="Service unavailable")

    # Parse comma-separated list params
    brand_list = [b.strip() for b in brands.split(",") if b.strip()] if brands else None
    fuel_list = [f.strip() for f in fuel.split(",") if f.strip()] if fuel else None
    car_type_list = [c.strip() for c in car_type.split(",") if c.strip()] if car_type else None

    try:
        result = await ultra_optimized_scrape_inserate(
            browser_manager=browser_manager,
            query=query,
            location=location,
            radius=radius,
            min_price=min_price,
            max_price=max_price,
            page_count=page_count,
            min_publish_date=min_publish_date,
            # Structured filters
            category_slug=category_slug,
            category_id=category_id,
            year_from=year_from,
            year_to=year_to,
            brands=brand_list,
            fuel=fuel_list,
            transmission=transmission,
            car_type=car_type_list,
            mileage_from=mileage_from,
            art=art,
        )

        # Clean up response - remove excessive metrics for production
        if "task_metrics" in result:
            del result["task_metrics"]
        if "optimization_features" in result:
            del result["optimization_features"]

        # Simplify performance metrics
        if "performance_metrics" in result:
            metrics = result["performance_metrics"]
            essential_metrics = {
                "pages_requested": metrics.get("pages_requested", 0),
                "pages_successful": metrics.get("pages_successful", 0),
                "success_rate": metrics.get("success_rate", 0),
                "average_page_time": metrics.get("average_page_time", 0),
            }
            result["performance_metrics"] = essential_metrics

        return result

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
