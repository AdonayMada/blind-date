"""
handlers/search.py
Handles the "Find a match" flow: entering the search queue, cancelling
a search, and being notified when a match is found.
"""

import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from pymongo.errors import PyMongoError

from database.db import get_db
from database.models import UserProfile, UserStatus
from keyboards.main_kb import in_chat_kb, main_menu_kb, searching_kb
from matching.match_service import find_match, leave_search_queue

logger = logging.getLogger(__name__)
router = Router(name="search")


async def _get_profile(telegram_id: int) -> UserProfile | None:
    """Fetches and parses a user's profile, returning None on failure."""
    db = get_db()
    try:
        doc = await db["users"].find_one({"telegram_id": telegram_id})
    except PyMongoError as exc:
        logger.error("DB error fetching profile %s: %s", telegram_id, exc)
        return None

    if doc is None:
        return None

    try:
        return UserProfile.from_mongo(doc)
    except Exception as exc:
        logger.error("Corrupt profile for %s: %s", telegram_id, exc)
        return None


@router.message(F.text == "🔍 Find a match")
async def start_search(message: Message, state: FSMContext, bot: Bot) -> None:
    """Starts the matchmaking search for the requesting user."""
    profile = await _get_profile(message.from_user.id)

    if profile is None:
        await message.answer("⚠️ Couldn't load your profile. Try /start.")
        return

    if profile.status == UserStatus.BANNED:
        await message.answer("🚫 Your account is banned.")
        return

    if not profile.is_profile_complete():
        await message.answer("⚠️ Please finish setting up your profile first. Use /start.")
        return

    if profile.status == UserStatus.IN_CHAT:
        await message.answer("You're already chatting with someone! Use 🛑 Stop chat first.")
        return

    if profile.status == UserStatus.SEARCHING:
        await message.answer("🔍 You're already searching. Please wait...", reply_markup=searching_kb())
        return

    await message.answer("🔍 Searching for your match...", reply_markup=searching_kb())

    try:
        match_result = await find_match(profile.telegram_id)
    except Exception as exc:
        logger.error("Error during matchmaking for %s: %s", profile.telegram_id, exc)
        await message.answer("⚠️ Something went wrong while searching. Please try again.")
        return

    if match_result is None:
        # No match found yet — user has been added to the search queue.
        return

    # A match was found immediately — notify both parties.
    partner_id = match_result

    try:
        await bot.send_message(
            chat_id=profile.telegram_id,
            text="💘 <b>Match found!</b> Say hello — you're now connected anonymously.",
            reply_markup=in_chat_kb(),
        )
        await bot.send_message(
            chat_id=partner_id,
            text="💘 <b>Match found!</b> Say hello — you're now connected anonymously.",
            reply_markup=in_chat_kb(),
        )
    except Exception as exc:
        # Message delivery failure shouldn't crash the flow; log and continue.
        logger.error(
            "Failed to notify matched users %s / %s: %s", profile.telegram_id, partner_id, exc
        )


@router.callback_query(F.data == "search:cancel")
async def cancel_search(callback: CallbackQuery) -> None:
    """Cancels an active search and removes the user from the queue."""
    try:
        removed = await leave_search_queue(callback.from_user.id)
    except Exception as exc:
        logger.error("Error cancelling search for %s: %s", callback.from_user.id, exc)
        await callback.answer("⚠️ Couldn't cancel search. Try again.", show_alert=True)
        return

    if removed:
        await callback.message.edit_text("❌ Search cancelled.")
        await callback.message.answer("Back to the main menu:", reply_markup=main_menu_kb())
    else:
        await callback.answer("You weren't in the search queue.", show_alert=True)

    await callback.answer()