"""
handlers/start.py
Handles the /start command, initial user registration, and entry point
into the profile creation flow.
"""

import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from pymongo.errors import PyMongoError

from database.db import get_db
from database.models import UserProfile, UserStatus
from keyboards.main_kb import main_menu_kb
from utils.states import RegistrationStates

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Entry point for new and returning users.
    - New users: create a base profile document and begin registration.
    - Returning users with complete profiles: show main menu.
    - Returning users with incomplete profiles: resume registration.
    """
    await state.clear()
    db = get_db()
    users = db["users"]

    try:
        existing = await users.find_one({"telegram_id": message.from_user.id})
    except PyMongoError as exc:
        logger.error("DB error fetching user %s: %s", message.from_user.id, exc)
        await message.answer(
            "⚠️ We're having trouble connecting to our database. Please try again shortly."
        )
        return

    if existing is None:
        # Brand new user — create a minimal profile document
        try:
            new_profile = UserProfile(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                status=UserStatus.NEW,
            )
            doc = new_profile.to_mongo()
            doc["telegram_id"] = message.from_user.id
            await users.insert_one(doc)
            logger.info("New user registered: %s", message.from_user.id)
        except PyMongoError as exc:
            logger.error("Failed to insert new user %s: %s", message.from_user.id, exc)
            await message.answer("⚠️ Something went wrong while setting up your account. Try /start again.")
            return

        await message.answer(
            "💘 <b>Welcome to Blind Date Bot!</b>\n\n"
            "Let's set up your profile so we can find you great matches.\n\n"
            "First, what's your name?"
        )
        await state.set_state(RegistrationStates.waiting_for_name)
        return

    # Returning user
    try:
        profile = UserProfile.from_mongo(existing)
    except Exception as exc:
        logger.error("Corrupt profile data for user %s: %s", message.from_user.id, exc)
        await message.answer("⚠️ Your profile data seems corrupted. Please contact support.")
        return

    if profile.status == UserStatus.BANNED:
        await message.answer("🚫 Your account has been banned from using this bot.")
        return

    if profile.is_profile_complete():
        await message.answer(
            f"👋 Welcome back, <b>{profile.name}</b>!\n\nUse the menu below to get started.",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(
            "👋 Welcome back! Let's finish setting up your profile.\n\nWhat's your name?"
        )
        await state.set_state(RegistrationStates.waiting_for_name)


@router.message(F.text == "❓ Help")
@router.message(F.text == "/help")
async def cmd_help(message: Message) -> None:
    """Displays help information about how the bot works."""
    await message.answer(
        "ℹ️ <b>How Blind Date Bot works:</b>\n\n"
        "1️⃣ Complete your profile (name, age, gender, city, bio).\n"
        "2️⃣ Tap 🔍 <b>Find a match</b> to start searching.\n"
        "3️⃣ Once matched, chat anonymously with your partner.\n"
        "4️⃣ Use ⏭ <b>Next</b> to move on, or 🛑 <b>Stop</b> to end the chat.\n"
        "5️⃣ Report any inappropriate behavior with 🚩 <b>Report</b>.\n\n"
        "Stay respectful and have fun! 💕"
    )
