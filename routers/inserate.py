import time
from fastapi import APIRouter, Query
from scrapers.inserate import get_inserate_klaz
from utils.browser import PlaywrightManager

router = APIRouter()


@router.get("/inserate")
async def get_inserate(
    query: str = Query(None),
    location: str = Query(None),
    radius: int = Query(None),
    min_price: int = Query(None),
    max_price: int = Query(None),
    page_count: int = Query(1, ge=1, le=20),
):
    browser_manager = PlaywrightManager()
    await browser_manager.start()
    try:
        start_time = time.time()
        results = await get_inserate_klaz(
            browser_manager, query, location, radius, min_price, max_price, page_count
        )
        end_time = time.time()
        print(f"Time taken: {end_time - start_time} seconds")
        # Remove duplicates based on 'adid'
        seen_adids = set()
        unique_results = []
        for result in results:
            if result["adid"] not in seen_adids:
                unique_results.append(result)
                seen_adids.add(result["adid"])

        return {
            "success": True,
            "time_taken": end_time - start_time,
            "unique_results": len(unique_results),
            "data": unique_results,
        }
    finally:
        await browser_manager.close()
