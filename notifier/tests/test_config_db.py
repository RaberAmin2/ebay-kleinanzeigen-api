"""
Unit tests for notifier/config.py and notifier/db.py.

Run with: pytest notifier/tests/ -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from notifier.config import NotifierConfig, SearchConfig, ProfileConfig
from notifier.db import NotifierDB


# ── Config tests ──────────────────────────────────────────────────────────


def _write_yaml(path: Path, content: str) -> NotifierConfig:
    path.write_text(content, encoding="utf-8")
    return NotifierConfig(path)


def test_minimal_config():
    cfg = _write_yaml(
        Path(tempfile.mktemp(suffix=".yaml")),
        """
api_base_url: "http://localhost:8000"
profiles:
  testuser:
    telegram_chat_id: "12345"
    telegram_token: "dummy"
    searches:
      - name: "Test Search"
        params:
          query: "test"
""",
    )
    assert cfg.api_base_url == "http://localhost:8000"
    assert len(cfg.profiles) == 1
    assert cfg.profiles[0].name == "testuser"
    assert cfg.profiles[0].telegram_chat_id == "12345"
    assert len(cfg.profiles[0].searches) == 1
    assert cfg.profiles[0].searches[0].name == "Test Search"


def test_validate_valid_config():
    cfg = _write_yaml(
        Path(tempfile.mktemp(suffix=".yaml")),
        """
api_base_url: "http://localhost:8000"
profiles:
  u1:
    telegram_chat_id: "123"
    telegram_token: "tok"
    searches:
      - name: "s1"
        params:
          query: "x"
""",
    )
    assert cfg.validate() == []


def test_validate_missing_api_url():
    cfg = _write_yaml(
        Path(tempfile.mktemp(suffix=".yaml")),
        """
profiles:
  u1:
    telegram_chat_id: "123"
    telegram_token: "tok"
    searches:
      - name: "s1"
        params:
          query: "x"
""",
    )
    errors = cfg.validate()
    assert any("api_base_url" in e for e in errors)


def test_validate_no_profiles():
    cfg = _write_yaml(
        Path(tempfile.mktemp(suffix=".yaml")),
        'api_base_url: "http://localhost:8000"',
    )
    errors = cfg.validate()
    assert any("profile" in e.lower() for e in errors)


def test_validate_missing_chat_id():
    cfg = _write_yaml(
        Path(tempfile.mktemp(suffix=".yaml")),
        """
api_base_url: "http://localhost:8000"
profiles:
  u1:
    telegram_token: "tok"
    searches:
      - name: "s1"
        params:
          query: "x"
""",
    )
    errors = cfg.validate()
    assert any("chat_id" in e for e in errors)


def test_validate_unknown_params():
    cfg = _write_yaml(
        Path(tempfile.mktemp(suffix=".yaml")),
        """
api_base_url: "http://localhost:8000"
profiles:
  u1:
    telegram_chat_id: "123"
    telegram_token: "tok"
    searches:
      - name: "s1"
        params:
          query: "x"
          invalid_param: 123
""",
    )
    errors = cfg.validate()
    assert any("invalid_param" in e for e in errors)


def test_validate_interval_negative():
    cfg = _write_yaml(
        Path(tempfile.mktemp(suffix=".yaml")),
        """
api_base_url: "http://localhost:8000"
profiles:
  u1:
    telegram_chat_id: "123"
    telegram_token: "tok"
    searches:
      - name: "s1"
        params:
          query: "x"
        interval_minutes: 0
""",
    )
    errors = cfg.validate()
    assert any("interval_minutes" in e for e in errors)


def test_paused_searches_excluded():
    cfg = _write_yaml(
        Path(tempfile.mktemp(suffix=".yaml")),
        """
api_base_url: "http://localhost:8000"
profiles:
  u1:
    telegram_chat_id: "123"
    telegram_token: "tok"
    searches:
      - name: "active"
        params:
          query: "x"
      - name: "paused"
        params:
          query: "y"
        paused: true
""",
    )
    assert len(cfg.all_searches) == 1
    assert cfg.all_searches[0].name == "active"


def test_env_token_fallback():
    import os
    os.environ["TELEGRAM_BOT_TOKEN"] = "env-token"
    try:
        cfg = _write_yaml(
            Path(tempfile.mktemp(suffix=".yaml")),
            """
api_base_url: "http://localhost:8000"
profiles:
  u1:
    telegram_chat_id: "123"
    searches:
      - name: "s1"
        params:
          query: "x"
""",
        )
        assert cfg.profiles[0].telegram_token == "env-token"
    finally:
        del os.environ["TELEGRAM_BOT_TOKEN"]


# ── DB tests ───────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Create a temporary in-memory DB for testing."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    database = NotifierDB(db_path)
    yield database
    database.close()
    db_path.unlink(missing_ok=True)


def test_ensure_profile(db):
    pid1 = db.ensure_profile("user1")
    pid2 = db.ensure_profile("user1")
    assert pid1 == pid2  # idempotent
    pid3 = db.ensure_profile("user2")
    assert pid3 != pid1


def test_ensure_search(db):
    sid = db.ensure_search("profile1", "search1")
    assert sid > 0
    sid2 = db.ensure_search("profile1", "search1")
    assert sid == sid2  # idempotent


def test_seen_listings(db):
    sid = db.ensure_search("p1", "s1")
    assert not db.is_seen(sid, "ad123")
    count = db.mark_seen(sid, ["ad123", "ad456"])
    assert count == 2
    assert db.is_seen(sid, "ad123")
    assert db.is_seen(sid, "ad456")
    # Double-mark should not increase count
    count = db.mark_seen(sid, ["ad123"])
    assert count == 0


def test_filter_new(db):
    sid = db.ensure_search("p1", "s1")
    db.mark_seen(sid, ["ad1", "ad2"])
    new = db.filter_new(sid, ["ad1", "ad2", "ad3", "ad4"])
    assert new == ["ad3", "ad4"]


def test_filter_new_empty(db):
    sid = db.ensure_search("p1", "s1")
    assert db.filter_new(sid, []) == []


def test_last_run_at_initially_none(db):
    sid = db.ensure_search("p1", "s1")
    assert db.last_run_at(sid) is None


def test_log_run_updates_last_run(db):
    sid = db.ensure_search("p1", "s1")
    db.log_run(sid, listings_found=10, new_listings=3)
    last = db.last_run_at(sid)
    assert last is not None
    assert "T" in last  # ISO 8601 format after normalization


def test_notification_logging(db):
    sid = db.ensure_search("p1", "s1")
    db.log_notification(sid, "ad999")
    stats = db.stats()
    assert stats["total_notifications"] == 1
    assert stats["total_runs"] == 0  # notifications don't count as runs


def test_stats(db):
    sid = db.ensure_search("p1", "s1")
    db.mark_seen(sid, ["a1", "a2", "a3"])
    db.log_run(sid, 3, 2)
    db.log_notification(sid, "a1")
    db.log_notification(sid, "a2")

    stats = db.stats()
    assert stats["seen_listings"] == 3
    assert stats["total_runs"] == 1
    assert stats["total_notifications"] == 2
    assert stats["last_run"] is not None
