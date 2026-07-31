"""
database/db.py
MongoDB Atlas connection management using Motor (async driver).

Provides a singleton-style client, database accessor, index setup,
and clean startup/shutdown hooks used by app.py.
"""

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def init_db() -> None:
    """Initializes the Motor client and verifies connectivity."""
    global _client, _db

    if _client is not None:
        logger.warning("init_db() called but client already initialized.")
        return

    try:
        _client = AsyncIOMotorClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=5000,
        )
        _db = _client[settings.MONGO_DB_NAME]

        # Verify the connection is actually alive
        await _client.admin.command("ping")
    except PyMongoError as exc:
        _client = None
        _db = None
        logger.critical("Could not connect to MongoDB Atlas: %s", exc)
        raise


async def close_db() -> None:
    """Closes the Motor client connection."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None


def get_db() -> AsyncIOMotorDatabase:
    """
    Returns the active database instance.
    Raises RuntimeError if called before init_db().
    """
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def ensure_indexes() -> None:
    """Creates required indexes for collections. Safe to call repeatedly."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    try:
        users = _db["users"]
        await users.create_index("telegram_id", unique=True)
        await users.create_index("status")
        await users.create_index([("gender", 1), ("looking_for", 1), ("status", 1)])

        matches = _db["matches"]
        await matches.create_index([("user_a_id", 1), ("user_b_id", 1)])
        await matches.create_index("created_at")

        reports = _db["reports"]
        await reports.create_index("reported_id")

        logger.info("Database indexes verified/created successfully.")
    except PyMongoError as exc:
        logger.error("Failed to create indexes: %s", exc)
        raise
