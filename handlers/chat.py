"""
handlers/chat.py
Handles in-chat interactions: relaying messages between matched partners,
"Next partner", "Stop chat", and "Report" actions.
"""

import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from pymongo.errors import PyMongoError

from database.db import get_db
from database.models import Report, UserProfile, UserStatus
from keyboards.main_kb import in_chat_kb, main_menu_kb, searching_kb
from matching.match_service import end_chat, find_match

logger = logging.getLogger(__name__)
router = Router(name="chat")

# Message types that are safe to relay as-is between partners.
_RELAYABLE_CONTENT = (
    "text",
    "photo",
    "sticker",
    "voice",
    "video",
    "video_note",
    "animation",
    "document",
    "audio",
)


async def _get_profile(telegram_id: int) -> UserProfile | None:
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


@router.message(F.content_type.in_(_RELAYABLE_CONTENT))
async def relay_message(message: Message, bot: Bot) -> None:
    """
    Relays any message from a user currently IN_CHAT to their partner.
    This handler only fires for content types we explicitly support;
    unmatched users simply fall through (handled by other routers/menu text).
    """
    profile = await _get_profile(message.from_user.id)

    if profile is None or profile.status != UserStatus.IN_CHAT or not profile.current_partner_id:
        # Not in an active chat — ignore silently, let other handlers process it
        # (e.g. reply keyboard text like "👤 My profile" also has content_type "text").
        return

    partner_id = profile.current_partner_id

    try:
        await bot.copy_message(
            chat_id=partner_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as exc:
        logger.warning("Failed to relay message from %s to %s: %s", profile.telegram_id, partner_id, exc)
        await message.answer("⚠️ Couldn't deliver your message. Your partner may have blocked the bot.")


@router.callback_query(F.data == "chat:stop")
async def stop_chat(callback: CallbackQuery, bot: Bot) -> None:
    """Ends the current chat for both users."""
    profile = await _get_profile(callback.from_user.id)

    if profile is None or profile.status != UserStatus.IN_CHAT:
        await callback.answer("You're not in a chat right now.", show_alert=True)
        return

    partner_id = profile.current_partner_id

    try:
        await end_chat(profile.telegram_id, reason="manual_stop")
    except Exception as exc:
        logger.error("Error ending chat for %s: %s", profile.telegram_id, exc)
        await callback.answer("⚠️ Couldn't end chat. Try again.", show_alert=True)
        return

    await callback.message.edit_text("🛑 Chat ended.")
    await callback.message.answer("Back to the main menu:", reply_markup=main_menu_kb())

    if partner_id:
        try:
            await bot.send_message(
                chat_id=partner_id,
                text="🛑 Your partner has ended the chat.",
                reply_markup=main_menu_kb(),
            )
        except Exception as exc:
            logger.warning("Failed to notify partner %s of chat end: %s", partner_id, exc)

    await callback.answer()


@router.callback_query(F.data == "chat:next")
async def next_partner(callback: CallbackQuery, bot: Bot) -> None:
    """Ends the current chat and immediately starts a new search."""
    profile = await _get_profile(callback.from_user.id)

    if profile is None or profile.status != UserStatus.IN_CHAT:
        await callback.answer("You're not in a chat right now.", show_alert=True)
        return

    old_partner_id = profile.current_partner_id

    try:
        await end_chat(profile.telegram_id, reason="next_partner")
    except Exception as exc:
        logger.error("Error ending chat for %s: %s", profile.telegram_id, exc)
        await callback.answer("⚠️ Couldn't switch partner. Try again.", show_alert=True)
        return

    if old_partner_id:
        try:
            await bot.send_message(
                chat_id=old_partner_id,
                text="🛑 Your partner has left the chat.",
                reply_markup=main_menu_kb(),
            )
        except Exception as exc:
            logger.warning("Failed to notify old partner %s: %s", old_partner_id, exc)

    await callback.message.edit_text("⏭ Looking for a new match...")
    await callback.message.answer("🔍 Searching...", reply_markup=searching_kb())

    try:
        match_result = await find_match(profile.telegram_id)
    except Exception as exc:
        logger.error("Error during matchmaking for %s: %s", profile.telegram_id, exc)
        await callback.message.answer("⚠️ Something went wrong while searching.")
        await callback.answer()
        return

    if match_result is not None:
        partner_id = match_result
        try:
            await bot.send_message(
                chat_id=profile.telegram_id,
                text="💘 <b>Match found!</b> Say hello!",
                reply_markup=in_chat_kb(),
            )
            await bot.send_message(
                chat_id=partner_id,
                text="💘 <b>Match found!</b> Say hello!",
                reply_markup=in_chat_kb(),
            )
        except Exception as exc:
            logger.error("Failed to notify matched users: %s", exc)

    await callback.answer()


@router.callback_query(F.data == "chat:report")
async def report_partner(callback: CallbackQuery, bot: Bot) -> None:
    """Files a report against the current chat partner and ends the chat."""
    profile = await _get_profile(callback.from_user.id)

    if profile is None or profile.status != UserStatus.IN_CHAT or not profile.current_partner_id:
        await callback.answer("You're not in a chat right now.", show_alert=True)
        return

    partner_id = profile.current_partner_id
    db = get_db()

    try:
        report = Report(
            reporter_id=profile.telegram_id,
            reported_id=partner_id,
            reason="reported_via_chat_button",
        )
        await db["reports"].insert_one(report.to_mongo())
    except PyMongoError as exc:
        logger.error("Failed to save report from %s against %s: %s", profile.telegram_id, partner_id, exc)
        await callback.answer("⚠️ Couldn't submit report. Try again.", show_alert=True)
        return

    try:
        await end_chat(profile.telegram_id, reason="reported")
    except Exception as exc:
        logger.error("Error ending chat after report for %s: %s", profile.telegram_id, exc)

    await callback.message.edit_text("🚩 Report submitted. The chat has been ended.")
    await callback.message.answer("Back to the main menu:", reply_markup=main_menu_kb())

    try:
        await bot.send_message(
            chat_id=partner_id,
            text="🛑 Your partner has ended the chat.",
            reply_markup=main_menu_kb(),
        )
    except Exception as exc:
        logger.warning("Failed to notify reported partner %s: %s", partner_id, exc)

    await callback.answer()
