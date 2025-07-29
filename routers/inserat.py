import time
from scrapers.inserat import get_inserate_details
from fastapi import APIRouter
from utils.browser import PlaywrightManager

router = APIRouter()


@router.get("/inserat/{id}")
async def get_inserat(id: str):
    browser_manager = PlaywrightManager()
    await browser_manager.start()
    try:
        start_time = time.time()
        page = await browser_manager.new_context_page()
        url = f"https://www.kleinanzeigen.de/s-anzeige/{id}"
        result = await get_inserate_details(url, page)
        return {"success": True, "time_taken": time.time() - start_time, "data": result}
    finally:
        await browser_manager.close()
