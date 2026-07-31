"""
handlers/admin.py
Basic moderation commands restricted to Telegram IDs listed in ADMIN_IDS.
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from pymongo.errors import PyMongoError

from config import settings
from database.db import get_db
from database.models import UserStatus

logger = logging.getLogger(__name__)
router = Router(name="admin")


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.ADMIN_IDS


@router.message(Command("ban"))
async def ban_user(message: Message) -> None:
    """Usage: /ban <telegram_id>"""
    if not _is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Usage: /ban <telegram_id>")
        return

    target_id = int(parts[1])
    db = get_db()

    try:
        result = await db["users"].update_one(
            {"telegram_id": target_id},
            {"$set": {"status": UserStatus.BANNED.value, "current_partner_id": None}},
        )
    except PyMongoError as exc:
        logger.error("Failed to ban user %s: %s", target_id, exc)
        await message.answer("⚠️ Database error while banning.")
        return

    if result.matched_count == 0:
        await message.answer(f"No user found with ID {target_id}.")
    else:
        await message.answer(f"🚫 User {target_id} has been banned.")


@router.message(Command("unban"))
async def unban_user(message: Message) -> None:
    """Usage: /unban <telegram_id>"""
    if not _is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Usage: /unban <telegram_id>")
        return

    target_id = int(parts[1])
    db = get_db()

    try:
        result = await db["users"].update_one(
            {"telegram_id": target_id},
            {"$set": {"status": UserStatus.ACTIVE.value}},
        )
    except PyMongoError as exc:
        logger.error("Failed to unban user %s: %s", target_id, exc)
        await message.answer("⚠️ Database error while unbanning.")
        return

    if result.matched_count == 0:
        await message.answer(f"No user found with ID {target_id}.")
    else:
        await message.answer(f"✅ User {target_id} has been unbanned.")


@router.message(Command("stats"))
async def stats(message: Message) -> None:
    """Usage: /stats — shows basic platform counts."""
    if not _is_admin(message.from_user.id):
        return

    db = get_db()
    try:
        total = await db["users"].count_documents({})
        active = await db["users"].count_documents({"status": UserStatus.ACTIVE.value})
        searching = await db["users"].count_documents({"status": UserStatus.SEARCHING.value})
        in_chat = await db["users"].count_documents({"status": UserStatus.IN_CHAT.value})
        banned = await db["users"].count_documents({"status": UserStatus.BANNED.value})
        reports = await db["reports"].count_documents({})
    except PyMongoError as exc:
        logger.error("Failed to fetch stats: %s", exc)
        await message.answer("⚠️ Database error while fetching stats.")
        return

    await message.answer(
        f"📊 <b>Bot Stats</b>\n\n"
        f"Total users: {total}\n"
        f"Active: {active}\n"
        f"Searching: {searching}\n"
        f"In chat: {in_chat}\n"
        f"Banned: {banned}\n"
        f"Reports filed: {reports}"
    )
