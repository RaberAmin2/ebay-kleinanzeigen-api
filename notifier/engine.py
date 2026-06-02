"""
Async polling engine — fetches listings from the API and detects new ones.

Pure business logic: reads config + calls API + checks DB + sends to notifier.
No knowledge of Telegram, CLI, or daemon — those are separate layers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import httpx

from notifier.config import NotifierConfig, SearchConfig
from notifier.db import NotifierDB

logger = logging.getLogger(__name__)

# Callable invoked for each newly discovered listing.
# Receives (profile_name, search_name, listing_dict).
NewListingCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class PollingEngine:
    """Polls the Kleinanzeigen API for configured searches and detects new listings."""

    def __init__(
        self,
        config: NotifierConfig,
        db: NotifierDB,
        on_new_listing: NewListingCallback | None = None,
    ):
        self.config = config
        self.db = db
        self.on_new_listing = on_new_listing
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.api_base_url,
                timeout=httpx.Timeout(120.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def poll_search(self, search: SearchConfig) -> dict[str, Any]:
        """Poll a single search. Returns a result dict with counts."""
        search_id = self.db.ensure_search(search.profile_name, search.name)
        last_run = self.db.last_run_at(search_id)

        params: dict[str, Any] = dict(search.params)
        if last_run:
            params["min_publish_date"] = last_run

        logger.info(
            "Polling '%s/%s' (last_run=%s)",
            search.profile_name, search.name, last_run or "never",
        )

        result = {
            "profile": search.profile_name,
            "search": search.name,
            "listings_found": 0,
            "new_listings": 0,
            "error": None,
        }

        try:
            resp = await self.client.get("/inserate", params=params)
            if resp.status_code == 503:
                result["error"] = "API unavailable (503)"
                self.db.log_run(search_id, error_msg=result["error"])
                return result
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            result["error"] = f"HTTP error: {e}"
            self.db.log_run(search_id, error_msg=result["error"])
            logger.error("Poll failed for '%s/%s': %s", search.profile_name, search.name, e)
            return result
        except Exception as e:
            result["error"] = f"Unexpected error: {e}"
            self.db.log_run(search_id, error_msg=result["error"])
            logger.error("Poll failed for '%s/%s': %s", search.profile_name, search.name, e)
            return result

        results = data.get("results", []) or data.get("data", [])
        if not results:
            self.db.log_run(search_id, listings_found=0, new_listings=0)
            result["listings_found"] = 0
            return result

        all_adids = [item.get("adid", "") for item in results if item.get("adid")]
        new_adids = self.db.filter_new(search_id, all_adids)

        result["listings_found"] = len(all_adids)
        result["new_listings"] = len(new_adids)

        # Notify for each new listing
        if new_adids and self.on_new_listing:
            for item in results:
                adid = item.get("adid", "")
                if adid in new_adids:
                    await self.on_new_listing(search.profile_name, search.name, item)

        # Mark all as seen (even old ones — they're already filtered)
        self.db.mark_seen(search_id, all_adids)
        self.db.log_run(
            search_id,
            listings_found=len(all_adids),
            new_listings=len(new_adids),
        )

        if new_adids:
            logger.info(
                "'%s/%s': %d new listings out of %d found",
                search.profile_name, search.name, len(new_adids), len(all_adids),
            )

        return result

    async def poll_all(self) -> list[dict[str, Any]]:
        """Run all non-paused searches once. Returns results per search."""
        results: list[dict[str, Any]] = []
        for search in self.config.all_searches:
            r = await self.poll_search(search)
            results.append(r)
        return results

    async def poll_loop(self, stop_event: asyncio.Event | None = None) -> None:
        """
        Run continuous polling with per-search intervals.
        Call `stop_event.set()` from another coroutine / signal handler to stop.
        """
        if stop_event is None:
            stop_event = asyncio.Event()

        # Track next poll time per search
        next_poll: dict[str, float] = {}  # search_key -> timestamp

        while not stop_event.is_set():
            now = datetime.now(timezone.utc).timestamp()

            for search in self.config.all_searches:
                key = f"{search.profile_name}/{search.name}"
                if now >= next_poll.get(key, 0):
                    await self.poll_search(search)
                    next_poll[key] = now + (search.interval_minutes * 60)

            # Sleep until the next due poll, checking stop_event every second
            sleep_time = 60  # default: check every minute
            if next_poll:
                soonest = min(next_poll.values())
                sleep_time = max(1, soonest - datetime.now(timezone.utc).timestamp())

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=sleep_time)
                break  # stop_event was set
            except asyncio.TimeoutError:
                pass  # timeout means keep polling
