"""
Kleinanzeigen Search Notifier — configuration reader and validator.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

# All query params accepted by GET /inserate
VALID_INCREATE_PARAMS = frozenset({
    "query", "location", "radius",
    "min_price", "max_price",
    "page_count", "min_publish_date",
    "category_slug", "category_id",
    "year_from", "year_to",
    "brands", "fuel",
    "transmission", "car_type",
    "mileage_from", "art",
})


class SearchConfig:
    """A single saved search."""

    def __init__(self, data: dict, profile_name: str):
        self.profile_name = profile_name
        self.name: str = data["name"]
        self.params: dict[str, Any] = data.get("params", {})
        self.interval_minutes: int = data.get("interval_minutes", 15)
        self.paused: bool = data.get("paused", False)

    def __repr__(self) -> str:
        return f"SearchConfig({self.profile_name}/{self.name})"


class ProfileConfig:
    """A user profile with Telegram credentials and searches."""

    def __init__(self, name: str, data: dict):
        self.name = name
        self.telegram_chat_id: str = str(data.get("telegram_chat_id", ""))
        self.telegram_token: str = data.get(
            "telegram_token",
            os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        )
        self.searches: list[SearchConfig] = [
            SearchConfig(s, name) for s in data.get("searches", [])
        ]

    def __repr__(self) -> str:
        return f"ProfileConfig({self.name}, {len(self.searches)} searches)"


class NotifierConfig:
    """Top-level configuration loaded from searches.yaml."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with open(self.path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        self.api_base_url: str = (raw.get("api_base_url") or "").rstrip("/")
        self.profiles: list[ProfileConfig] = [
            ProfileConfig(name, data)
            for name, data in raw.get("profiles", {}).items()
        ]

    @property
    def all_searches(self) -> list[SearchConfig]:
        """Flat list of all non-paused searches across all profiles."""
        result: list[SearchConfig] = []
        for profile in self.profiles:
            for search in profile.searches:
                if not search.paused:
                    result.append(search)
        return result

    def validate(self) -> list[str]:
        """Validate the configuration. Returns a list of error messages (empty = valid)."""
        errors: list[str] = []

        if not self.api_base_url:
            errors.append("api_base_url is required (e.g. 'http://localhost:8000')")

        if not self.profiles:
            errors.append("At least one profile is required under 'profiles:'")

        for profile in self.profiles:
            if not profile.telegram_chat_id:
                errors.append(
                    f"Profile '{profile.name}': telegram_chat_id is required"
                )
            if not profile.telegram_token:
                errors.append(
                    f"Profile '{profile.name}': telegram_token is required "
                    "(or set TELEGRAM_BOT_TOKEN env var)"
                )
            if not profile.searches:
                errors.append(
                    f"Profile '{profile.name}': at least one search is required"
                )

            for search in profile.searches:
                if not search.name:
                    errors.append(
                        f"Profile '{profile.name}': search name is required"
                    )
                if not search.params:
                    errors.append(
                        f"Profile '{profile.name}' / '{search.name}': "
                        "params must not be empty"
                    )

                unknown = set(search.params) - VALID_INCREATE_PARAMS
                if unknown:
                    errors.append(
                        f"Profile '{profile.name}' / '{search.name}': "
                        f"unknown params: {', '.join(sorted(unknown))}"
                    )

                if search.interval_minutes < 1:
                    errors.append(
                        f"Profile '{profile.name}' / '{search.name}': "
                        "interval_minutes must be >= 1"
                    )

        return errors

    def get_profile(self, name: str) -> Optional[ProfileConfig]:
        for p in self.profiles:
            if p.name == name:
                return p
        return None

    def get_search(self, profile_name: str, search_name: str) -> Optional[SearchConfig]:
        profile = self.get_profile(profile_name)
        if not profile:
            return None
        for s in profile.searches:
            if s.name == search_name:
                return s
        return None

    def to_dict(self) -> dict:
        """Serialize back to a dict suitable for YAML dumping."""
        profiles_dict: dict[str, dict] = {}
        for profile in self.profiles:
            profiles_dict[profile.name] = {
                "telegram_chat_id": profile.telegram_chat_id,
                "telegram_token": profile.telegram_token,
                "searches": [
                    {
                        "name": s.name,
                        "params": s.params,
                        "interval_minutes": s.interval_minutes,
                        "paused": s.paused,
                    }
                    for s in profile.searches
                ],
            }
        return {
            "api_base_url": self.api_base_url,
            "profiles": profiles_dict,
        }

    def save(self) -> None:
        """Write the current config back to disk."""
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, allow_unicode=True, sort_keys=False)
