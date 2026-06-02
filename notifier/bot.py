"""
Interactive Telegram bot for managing Kleinanzeigen searches.

Commands:
  /start          — Welcome message and profile info
  /searches       — List all your searches
  /addsearch      — Guided wizard to add a new search
  /removesearch   — Remove a search by name
  /pause          — Pause a search
  /resume         — Resume a paused search
  /pollnow        — Trigger an immediate poll for your searches
  /stats          — Show database statistics
  /help           — Show available commands
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from notifier.config import NotifierConfig, VALID_INCREATE_PARAMS
from notifier.db import NotifierDB
from notifier.engine import PollingEngine
from notifier.notify.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

# Conversation states for /addsearch wizard
ASK_NAME, ASK_QUERY, ASK_CATEGORY, ASK_BRANDS, ASK_YEAR_FROM, ASK_MAX_PRICE, ASK_INTERVAL = range(7)

# Common categories and filter presets for quick selection
CATEGORIES = [
    ("Autos", "s-autos"),
    ("Wohnwagen / Mobile", "s-wohnwagen-mobile"),
    ("Motorräder", "s-motorraeder"),
    ("Immobilien", "s-immobilien"),
]

FUEL_OPTIONS = ["benzin", "diesel", "lpg", "cng", "elektro", "hybrid"]
TRANSMISSION_OPTIONS = ["automatik", "manuell"]
CAR_TYPE_OPTIONS = ["kombi", "suv", "limousine", "cabrio", "coupe", "kleinwagen", "van", "pickup"]


class NotifierBot:
    """Telegram bot for managing Kleinanzeigen search notifications."""

    def __init__(self, config_path: str, db_path: str):
        self.config_path = config_path
        self.db_path = db_path
        self.config: NotifierConfig | None = None
        self.db: NotifierDB | None = None
        self.engine: PollingEngine | None = None
        self.notifier: TelegramNotifier | None = None

    def _reload(self) -> None:
        """Reload config from disk."""
        self.config = NotifierConfig(self.config_path)

    def _get_profile(self, chat_id: str) -> Any | None:
        """Find the profile matching this Telegram chat ID."""
        for p in self.config.profiles if self.config else []:
            if str(p.telegram_chat_id) == str(chat_id):
                return p
        return None

    def _require_profile(self, update: Update) -> Any | None:
        """Require a matching profile, or reply with an error."""
        chat_id = str(update.effective_chat.id) if update.effective_chat else ""
        profile = self._get_profile(chat_id)
        if not profile:
            asyncio.create_task(
                self._reply(update, "❌ Dein Telegram-Chat ist nicht in der Konfiguration "
                              "registriert. Füge deine Chat-ID zur `searches.yaml` hinzu.")
            )
            return None
        return profile

    async def _reply(self, update: Update, text: str, **kwargs) -> None:
        """Safely reply to a message, falling back to bot.send_message if needed."""
        msg = update.effective_message
        if msg:
            await msg.reply_text(text, **kwargs)
        elif update.effective_chat:
            await update.get_bot().send_message(
                chat_id=update.effective_chat.id, text=text, **kwargs
            )

    # ── Commands ────────────────────────────────────────────────────────

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._reload()
        profile = self._require_profile(update)
        if not profile:
            return

        active = [s for s in profile.searches if not s.paused]
        paused = [s for s in profile.searches if s.paused]

        msg = (
            f"👋 *Kleinanzeigen Notifier*\n\n"
            f"Profil: *{profile.name}*\n"
            f"Aktive Suchen: {len(active)}\n"
            f"Pausierte Suchen: {len(paused)}\n\n"
            f"Nutze /help für alle Befehle."
        )
        await self._reply(update, msg, parse_mode="Markdown")

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = (
            "📋 *Verfügbare Befehle*\n\n"
            "/searches — Alle Suchen anzeigen\n"
            "/addsearch — Neue Suche hinzufügen\n"
            "/removesearch — Suche entfernen\n"
            "/pause — Suche pausieren\n"
            "/resume — Suche fortsetzen\n"
            "/pollnow — Jetzt prüfen\n"
            "/stats — Statistiken\n"
            "/help — Diese Hilfe"
        )
        await self._reply(update, msg, parse_mode="Markdown")

    async def searches(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._reload()
        profile = self._require_profile(update)
        if not profile:
            return

        if not profile.searches:
            await self._reply(update, "Keine Suchen konfiguriert. Nutze /addsearch.")
            return

        for s in profile.searches:
            status = "⏸" if s.paused else "🟢"
            params = ", ".join(f"{k}={v}" for k, v in s.params.items())
            await self._reply(update, 
                f"{status} '{s.name}' — alle {s.interval_minutes} min\n"
                f"  {params}",
            )

    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._reload()
        profile = self._require_profile(update)
        if not profile:
            return

        name = " ".join(context.args) if context.args else ""
        if not name:
            await self._reply(update, "Nutzung: /pause <Suchname>")
            return

        for s in profile.searches:
            if s.name.lower() == name.lower():
                s.paused = True
                self.config.save()
                await self._reply(update, f"⏸ Suche '{s.name}' pausiert.")
                return

        await self._reply(update, f"❌ Suche '{name}' nicht gefunden.")

    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._reload()
        profile = self._require_profile(update)
        if not profile:
            return

        name = " ".join(context.args) if context.args else ""
        if not name:
            await self._reply(update, "Nutzung: /resume <Suchname>")
            return

        for s in profile.searches:
            if s.name.lower() == name.lower():
                s.paused = False
                self.config.save()
                await self._reply(update, f"🟢 Suche '{s.name}' fortgesetzt.")
                return

        await self._reply(update, f"❌ Suche '{name}' nicht gefunden.")

    async def removesearch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._reload()
        profile = self._require_profile(update)
        if not profile:
            return

        name = " ".join(context.args) if context.args else ""
        if not name:
            await self._reply(update, "Nutzung: /removesearch <Suchname>")
            return

        for i, s in enumerate(profile.searches):
            if s.name.lower() == name.lower():
                removed = profile.searches.pop(i)
                self.config.save()
                await self._reply(update, f"🗑 Suche '{removed.name}' entfernt.")
                return

        await self._reply(update, f"❌ Suche '{name}' nicht gefunden.")

    async def pollnow(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._reload()
        profile = self._require_profile(update)
        if not profile:
            return

        if not profile.searches:
            await self._reply(update, "Keine Suchen zum Prüfen.")
            return

        await self._reply(update, "🔍 Prüfe neue Inserate...")

        db = NotifierDB(self.db_path)
        notifier = None
        if profile.telegram_token:
            notifier = TelegramNotifier(profile.telegram_token)

        async def on_new(p_name: str, s_name: str, listing: dict[str, Any]) -> None:
            if notifier and profile.telegram_chat_id:
                await notifier.send_listing(profile.telegram_chat_id, listing, s_name)

        engine = PollingEngine(self.config, db, on_new_listing=on_new)

        try:
            for search in profile.searches:
                if not search.paused:
                    result = await engine.poll_search(search)
                    if result["error"]:
                        await self._reply(update, 
                            f"❌ {search.name}: {result['error']}"
                        )
                    elif result["new_listings"] == 0:
                        await self._reply(update, 
                            f"✅ {search.name}: keine neuen ({result['listings_found']} gesamt)"
                        )
                    else:
                        await self._reply(update, 
                            f"🆕 {search.name}: *{result['new_listings']} neue* "
                            f"({result['listings_found']} gesamt)",
                            parse_mode="Markdown",
                        )
        finally:
            await engine.close()
            if notifier:
                await notifier.close()
            db.close()

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        db = NotifierDB(self.db_path)
        try:
            s = db.stats()
            msg = (
                f"📊 *Statistiken*\n\n"
                f"Gesehene Inserate: {s['seen_listings']}\n"
                f"Poll-Durchläufe: {s['total_runs']}\n"
                f"Benachrichtigungen: {s['total_notifications']}\n"
                f"Letzter Lauf: {s['last_run'] or 'nie'}"
            )
            await self._reply(update, msg, parse_mode="Markdown")
        finally:
            db.close()

    # ── /addsearch wizard ───────────────────────────────────────────────

    async def addsearch_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        self._reload()
        profile = self._require_profile(update)
        if not profile:
            return ConversationHandler.END

        context.user_data["add_profile"] = profile.name
        await self._reply(update, 
            "Wie soll die Suche heißen? (z.B. 'VW Golf Diesel')",
        )
        return ASK_NAME

    async def addsearch_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        name = update.message.text.strip()
        if not name:
            await self._reply(update, "Bitte gib einen Namen ein.")
            return ASK_NAME

        context.user_data["add_name"] = name

        await self._reply(update, 
            "Suchbegriff? (z.B. 'Klima', 'TDI')\n"
            "Oder '-' für keinen Suchbegriff."
        )
        return ASK_QUERY

    async def addsearch_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        if text and text != "-":
            context.user_data["add_query"] = text

        keyboard = [
            [InlineKeyboardButton(label, callback_data=f"cat_{value}")]
            for label, value in CATEGORIES
        ]
        await self._reply(update, 
            "Wähle eine Kategorie:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return ASK_CATEGORY

    async def addsearch_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        category = query.data.replace("cat_", "")
        context.user_data["add_category"] = category

        await query.edit_message_text(
            f"Kategorie: *{category}*\n\n"
            "Jetzt Marken (durch Komma getrennt), z.B. 'volkswagen,audi'\n"
            "Oder '-' für keine Marken-Filter.",
            parse_mode="Markdown",
        )
        return ASK_BRANDS

    async def addsearch_brands(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        if text and text != "-":
            context.user_data["add_brands"] = text

        await self._reply(update, 
            "Baujahr ab? (z.B. 2018)\nOder '-' für keinen Filter."
        )
        return ASK_YEAR_FROM

    async def addsearch_year(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        if text and text != "-" and text.isdigit():
            context.user_data["add_year_from"] = int(text)

        await self._reply(update, 
            "Maximalpreis in €? (z.B. 25000)\nOder '-' für keinen Filter."
        )
        return ASK_MAX_PRICE

    async def addsearch_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        if text and text != "-" and text.isdigit():
            context.user_data["add_max_price"] = int(text)

        await self._reply(update, 
            "Prüfintervall in Minuten? (z.B. 15)\nStandard: 15"
        )
        return ASK_INTERVAL

    async def addsearch_finish(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        interval = int(text) if text.isdigit() and int(text) > 0 else 15

        # Build params dict
        params: dict[str, Any] = {}
        if context.user_data.get("add_query"):
            params["query"] = context.user_data["add_query"]
        if context.user_data.get("add_category"):
            params["category_slug"] = context.user_data["add_category"]
        if context.user_data.get("add_brands"):
            params["brands"] = context.user_data["add_brands"]
        if context.user_data.get("add_year_from"):
            params["year_from"] = context.user_data["add_year_from"]
        if context.user_data.get("add_max_price"):
            params["max_price"] = context.user_data["add_max_price"]

        profile_name = context.user_data.get("add_profile", "")
        search_name = context.user_data.get("add_name", "Neue Suche")

        # Save to config
        self._reload()
        profile = self.config.get_profile(profile_name)
        if not profile:
            await self._reply(update, "❌ Profil nicht gefunden.")
            return ConversationHandler.END

        from notifier.config import SearchConfig
        profile.searches.append(SearchConfig({
            "name": search_name,
            "params": params,
            "interval_minutes": interval,
        }, profile_name))
        self.config.save()

        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
        await self._reply(update, 
            f"✅ Suche '{search_name}' hinzugefügt!\n"
            f"  {params_str}\n"
            f"  Intervall: {interval} min\n\n"
            f"Nutze /searches zum Anzeigen.",
        )

        context.user_data.clear()
        return ConversationHandler.END

    async def addsearch_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await self._reply(update, "Abgebrochen.")
        context.user_data.clear()
        return ConversationHandler.END

    # ── Run ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the bot (blocking)."""
        # Find a token from any profile
        self._reload()
        token = None
        for p in self.config.profiles if self.config else []:
            if p.telegram_token:
                token = p.telegram_token
                break

        if not token:
            raise ValueError(
                "Kein Telegram-Token gefunden. Setze telegram_token in searches.yaml "
                "oder TELEGRAM_BOT_TOKEN als Umgebungsvariable."
            )

        app = Application.builder().token(token).build()

        # Commands
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_cmd))
        app.add_handler(CommandHandler("searches", self.searches))
        app.add_handler(CommandHandler("pause", self.pause))
        app.add_handler(CommandHandler("resume", self.resume))
        app.add_handler(CommandHandler("removesearch", self.removesearch))
        app.add_handler(CommandHandler("pollnow", self.pollnow))
        app.add_handler(CommandHandler("stats", self.stats))

        # /addsearch wizard
        conv = ConversationHandler(
            entry_points=[CommandHandler("addsearch", self.addsearch_start)],
            states={
                ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addsearch_name)],
                ASK_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addsearch_query)],
                ASK_CATEGORY: [CallbackQueryHandler(self.addsearch_category, pattern="^cat_")],
                ASK_BRANDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addsearch_brands)],
                ASK_YEAR_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addsearch_year)],
                ASK_MAX_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addsearch_price)],
                ASK_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.addsearch_finish)],
            },
            fallbacks=[CommandHandler("cancel", self.addsearch_cancel)],
        )
        app.add_handler(conv)

        logger.info("🤖 Telegram bot starting...")
        app.run_polling()
