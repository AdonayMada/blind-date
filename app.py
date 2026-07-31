"""
app.py
Entry point for the Blind Date Bot.

Responsibilities:
- Initialize logging
- Initialize MongoDB (Motor) connection
- Initialize aiogram Bot & Dispatcher
- Register routers (handlers)
- Start polling with graceful shutdown
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from database.db import init_db, close_db, ensure_indexes

# Import routers from handlers
from handlers.start import router as start_router
from handlers.profile import router as profile_router
from handlers.search import router as search_router
from handlers.chat import router as chat_router
from handlers.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    """Runs once before polling starts."""
    try:
        await init_db()
        await ensure_indexes()
        logger.info("MongoDB connection established and indexes ensured.")
    except Exception as exc:
        logger.critical("Failed to initialize database: %s", exc)
        raise

    try:
        me = await bot.get_me()
        logger.info("Bot started as @%s (id=%s)", me.username, me.id)
    except Exception as exc:
        logger.critical("Failed to fetch bot info: %s", exc)
        raise


async def on_shutdown(bot: Bot) -> None:
    """Runs once when the bot is shutting down."""
    logger.info("Shutting down bot...")
    try:
        await close_db()
        logger.info("MongoDB connection closed cleanly.")
    except Exception as exc:
        logger.error("Error while closing MongoDB connection: %s", exc)

    try:
        await bot.session.close()
    except Exception as exc:
        logger.error("Error while closing bot session: %s", exc)


def create_dispatcher() -> Dispatcher:
    """Builds and configures the Dispatcher with all routers."""
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(profile_router)
    dp.include_router(search_router)
    dp.include_router(chat_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return dp


async def main() -> None:
    """Main coroutine: builds bot/dispatcher and starts polling."""
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher()

    try:
        # Drop any pending updates accumulated while the bot was offline
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as exc:
        logger.critical("Fatal error during polling: %s", exc)
        raise
    finally:
        logger.info("Polling stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
