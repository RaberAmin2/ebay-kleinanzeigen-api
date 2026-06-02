"""
Telegram notification backend — sends listing details to a Telegram chat.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import Bot
from telegram.error import TelegramError

from notifier.notify.base import BaseNotifier

logger = logging.getLogger(__name__)

# Max Telegram message length (4096 characters)
_MAX_LENGTH = 4000  # leave some headroom


def _format_listing(listing: dict[str, Any], search_name: str = "") -> str:
    """Format a listing dict into a Telegram message string."""
    title = listing.get("title", "Kein Titel")
    price = listing.get("price", "") or "VB"
    desc = listing.get("description", "")
    url = listing.get("url", "")
    published = listing.get("published_at", "")
    location_city = listing.get("location", {}).get("city", "") if isinstance(listing.get("location"), dict) else ""

    lines = [
        f"🔔 *Neues Inserat* — {search_name}" if search_name else "🔔 *Neues Inserat*",
        "",
        f"*{title.strip()[:200]}*",
        f"💰 {price} €",
    ]
    if location_city:
        lines.append(f"📍 {location_city}")
    if desc:
        lines.append(f"_{desc.strip()[:300]}_")
    if published:
        lines.append(f"📅 {published[:16].replace('T', ' ')}")

    lines.append("")
    lines.append(url)

    msg = "\n".join(lines)
    if len(msg) > _MAX_LENGTH:
        msg = msg[:_MAX_LENGTH - 3] + "..."
    return msg


class TelegramNotifier(BaseNotifier):
    """Sends notifications via Telegram Bot API."""

    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self._lock = asyncio.Lock()  # rate-limit sends

    async def send_listing(
        self,
        chat_id: str,
        listing: dict[str, Any],
        search_name: str = "",
    ) -> None:
        message = _format_listing(listing, search_name)
        await self._send_message(chat_id, message)

    async def send_text(self, chat_id: str, message: str) -> None:
        await self._send_message(chat_id, message)

    async def _send_message(self, chat_id: str, text: str) -> None:
        async with self._lock:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
            except TelegramError as e:
                logger.error("Telegram send failed (chat=%s): %s", chat_id, e)
                # Retry without Markdown if parse fails
                try:
                    await asyncio.sleep(1)
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        disable_web_page_preview=False,
                    )
                except TelegramError as e2:
                    logger.error("Telegram retry also failed: %s", e2)

    async def close(self) -> None:
        await self.bot.close()
