"""
Kleinanzeigen Search Notifier — Command-Line Interface.

Usage:
  python -m notifier.cli poll              # Run one polling cycle
  python -m notifier.cli daemon            # Start continuous polling
  python -m notifier.cli search list       # List all searches
  python -m notifier.cli config validate   # Validate searches.yaml
  python -m notifier.cli db stats          # Show database statistics
  python -m notifier.cli bot               # Start interactive Telegram bot
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any

import click

from notifier.config import NotifierConfig
from notifier.db import NotifierDB
from notifier.engine import PollingEngine
from notifier.notify.telegram import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("notifier")

DEFAULT_CONFIG = "notifier/searches.yaml"
DEFAULT_DB = "notifier/searches.db"


# ── Shared helpers ──────────────────────────────────────────────────────


def _load_config(config_path: str) -> NotifierConfig:
    cfg = NotifierConfig(config_path)
    errors = cfg.validate()
    if errors:
        click.echo("❌ Configuration errors:", err=True)
        for e in errors:
            click.echo(f"  • {e}", err=True)
        raise click.Abort()
    return cfg


async def _run_poll(config_path: str, db_path: str) -> None:
    """Run a single polling cycle and exit."""
    cfg = _load_config(config_path)
    db = NotifierDB(db_path)

    # Build per-profile notifiers
    notifiers: dict[str, TelegramNotifier] = {}
    for profile in cfg.profiles:
        if profile.telegram_token and profile.telegram_chat_id:
            notifiers[profile.name] = TelegramNotifier(profile.telegram_token)

    async def on_new(profile_name: str, search_name: str, listing: dict[str, Any]) -> None:
        notifier = notifiers.get(profile_name)
        if notifier:
            chat_id = cfg.get_profile(profile_name)
            if chat_id:
                await notifier.send_listing(chat_id.telegram_chat_id, listing, search_name)

    engine = PollingEngine(cfg, db, on_new_listing=on_new)
    try:
        results = await engine.poll_all()
        for r in results:
            status = "❌" if r["error"] else "✅"
            click.echo(f"  {status} {r['profile']}/{r['search']}: "
                        f"{r['new_listings']} new / {r['listings_found']} found"
                        + (f" ({r['error']})" if r["error"] else ""))
    finally:
        await engine.close()
        for n in notifiers.values():
            await n.close()
        db.close()


async def _run_daemon(config_path: str, db_path: str) -> None:
    """Run continuous polling until interrupted."""
    cfg = _load_config(config_path)
    db = NotifierDB(db_path)

    notifiers: dict[str, TelegramNotifier] = {}
    for profile in cfg.profiles:
        if profile.telegram_token and profile.telegram_chat_id:
            notifiers[profile.name] = TelegramNotifier(profile.telegram_token)

    async def on_new(profile_name: str, search_name: str, listing: dict[str, Any]) -> None:
        notifier = notifiers.get(profile_name)
        if notifier:
            chat_id = cfg.get_profile(profile_name)
            if chat_id:
                await notifier.send_listing(chat_id.telegram_chat_id, listing, search_name)

    engine = PollingEngine(cfg, db, on_new_listing=on_new)
    stop_event = asyncio.Event()

    def _handle_signal(signum, frame):
        click.echo("\nShutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    click.echo(f"🚀 Daemon started — {len(cfg.all_searches)} active search(es), "
               f"{len(cfg.profiles)} profile(s)")
    click.echo("Press Ctrl+C to stop.\n")

    try:
        await engine.poll_loop(stop_event)
    finally:
        await engine.close()
        for n in notifiers.values():
            await n.close()
        db.close()
        click.echo("Daemon stopped.")


# ── CLI ─────────────────────────────────────────────────────────────────


@click.group()
def cli():
    """Kleinanzeigen Search Notifier — poll for new listings and get notified."""
    pass


@cli.command()
@click.option("-c", "--config", default=DEFAULT_CONFIG, help="Path to searches.yaml")
@click.option("-d", "--db", "db_path", default=DEFAULT_DB, help="Path to SQLite database")
def poll(config: str, db_path: str):
    """Run a single polling cycle — fetch and notify for new listings."""
    asyncio.run(_run_poll(config, db_path))


@cli.command()
@click.option("-c", "--config", default=DEFAULT_CONFIG, help="Path to searches.yaml")
@click.option("-d", "--db", "db_path", default=DEFAULT_DB, help="Path to SQLite database")
def daemon(config: str, db_path: str):
    """Start continuous polling daemon (Ctrl+C to stop)."""
    asyncio.run(_run_daemon(config, db_path))


@cli.group()
def search():
    """Manage saved searches."""
    pass


@search.command("list")
@click.option("-c", "--config", default=DEFAULT_CONFIG, help="Path to searches.yaml")
def search_list(config: str):
    """List all configured searches."""
    cfg = NotifierConfig(config)
    if not cfg.profiles:
        click.echo("No profiles configured.")
        return

    for profile in cfg.profiles:
        click.echo(f"\n📁 {profile.name} (chat: {profile.telegram_chat_id or 'not set'})")
        if not profile.searches:
            click.echo("  (no searches)")
        for s in profile.searches:
            status = "⏸ paused" if s.paused else f"⏱ every {s.interval_minutes}m"
            params = ", ".join(f"{k}={v}" for k, v in s.params.items())
            click.echo(f"  {'🔴' if s.paused else '🟢'} {s.name} — {status}")
            click.echo(f"     params: {params}")


@cli.group()
def config_cmd():
    """Configuration utilities."""
    pass


@config_cmd.command("validate")
@click.option("-c", "--config", default=DEFAULT_CONFIG, help="Path to searches.yaml")
def config_validate(config: str):
    """Validate searches.yaml."""
    cfg = NotifierConfig(config)
    errors = cfg.validate()
    if errors:
        click.echo("❌ Configuration errors:", err=True)
        for e in errors:
            click.echo(f"  • {e}", err=True)
    else:
        click.echo(f"✅ Configuration valid — "
                    f"{len(cfg.profiles)} profile(s), "
                    f"{sum(len(p.searches) for p in cfg.profiles)} search(es)")


@cli.group()
def db_cmd():
    """Database utilities."""
    pass


@db_cmd.command("stats")
@click.option("-d", "--db", "db_path", default=DEFAULT_DB, help="Path to SQLite database")
def db_stats(db_path: str):
    """Show database statistics."""
    db = NotifierDB(db_path)
    try:
        stats = db.stats()
        click.echo(f"  Seen listings:    {stats['seen_listings']}")
        click.echo(f"  Total poll runs:  {stats['total_runs']}")
        click.echo(f"  Notifications:    {stats['total_notifications']}")
        click.echo(f"  Last run:         {stats['last_run'] or 'never'}")
    finally:
        db.close()


@cli.command()
@click.option("-c", "--config", default=DEFAULT_CONFIG, help="Path to searches.yaml")
@click.option("-d", "--db", "db_path", default=DEFAULT_DB, help="Path to SQLite database")
def bot(config: str, db_path: str):
    """Start interactive Telegram bot for managing searches."""
    from notifier.bot import NotifierBot
    click.echo("🤖 Starting Telegram bot...")
    bot_instance = NotifierBot(config, db_path)
    bot_instance.run()


if __name__ == "__main__":
    cli()
