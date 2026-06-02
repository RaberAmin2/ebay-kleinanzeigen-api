"""
Abstract base class for notification backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseNotifier(ABC):
    """Pluggable notification backend."""

    @abstractmethod
    async def send_listing(
        self,
        chat_id: str,
        listing: dict[str, Any],
        search_name: str = "",
    ) -> None:
        """Send a single listing notification."""
        ...

    @abstractmethod
    async def send_text(self, chat_id: str, message: str) -> None:
        """Send a plain text message."""
        ...

    async def close(self) -> None:
        """Clean up resources (optional override)."""
        pass
