"""
handlers/profile.py
Handles profile creation (registration flow) and profile editing.
"""

import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from pymongo.errors import PyMongoError

from config import settings
from database.db import get_db
from database.models import Gender, LookingFor, UserProfile, UserStatus
from keyboards.main_kb import main_menu_kb
from keyboards.profile_kb import (
    cancel_edit_kb,
    edit_profile_kb,
    gender_selection_kb,
    looking_for_kb,
    skip_photo_kb,
)
from utils.states import EditProfileStates, RegistrationStates

logger = logging.getLogger(__name__)
router = Router(name="profile")


async def _update_user(telegram_id: int, update: dict) -> bool:
    """Helper to update a user document safely. Returns True on success."""
    db = get_db()
    try:
        result = await db["users"].update_one(
            {"telegram_id": telegram_id}, {"$set": update}
        )
        return result.acknowledged
    except PyMongoError as exc:
        logger.error("Failed to update user %s: %s", telegram_id, exc)
        return False


# ---------------------------------------------------------------------------
# Registration flow
# ---------------------------------------------------------------------------

@router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()

    if not name or len(name) > 50:
        await message.answer("Please enter a valid name (1-50 characters).")
        return

    if not await _update_user(message.from_user.id, {"name": name}):
        await message.answer("⚠️ Couldn't save your name. Please try again.")
        return

    await state.set_state(RegistrationStates.waiting_for_age)
    await message.answer(f"Nice to meet you, {name}! 🎂 How old are you?")


@router.message(RegistrationStates.waiting_for_age)
async def process_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()

    if not text.isdigit():
        await message.answer("Please enter your age as a number (e.g. 25).")
        return

    age = int(text)
    if age < settings.MIN_AGE or age > settings.MAX_AGE:
        await message.answer(
            f"Age must be between {settings.MIN_AGE} and {settings.MAX_AGE}. Try again."
        )
        return

    if not await _update_user(message.from_user.id, {"age": age}):
        await message.answer("⚠️ Couldn't save your age. Please try again.")
        return

    await state.set_state(RegistrationStates.waiting_for_gender)
    await message.answer("Got it! What's your gender?", reply_markup=gender_selection_kb())


@router.callback_query(RegistrationStates.waiting_for_gender, F.data.startswith("gender:"))
async def process_gender(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        value = callback.data.split(":", 1)[1]
        gender = Gender(value)
    except (IndexError, ValueError):
        await callback.answer("Invalid selection.", show_alert=True)
        return

    if not await _update_user(callback.from_user.id, {"gender": gender.value}):
        await callback.answer("⚠️ Couldn't save. Try again.", show_alert=True)
        return

    await state.set_state(RegistrationStates.waiting_for_looking_for)
    await callback.message.edit_text("Who are you interested in meeting?")
    await callback.message.answer("Choose an option:", reply_markup=looking_for_kb())
    await callback.answer()


@router.callback_query(RegistrationStates.waiting_for_looking_for, F.data.startswith("looking_for:"))
async def process_looking_for(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        value = callback.data.split(":", 1)[1]
        looking_for = LookingFor(value)
    except (IndexError, ValueError):
        await callback.answer("Invalid selection.", show_alert=True)
        return

    if not await _update_user(callback.from_user.id, {"looking_for": looking_for.value}):
        await callback.answer("⚠️ Couldn't save. Try again.", show_alert=True)
        return

    await state.set_state(RegistrationStates.waiting_for_city)
    await callback.message.edit_text("Great choice! 🏙 Which city are you in?")
    await callback.answer()


@router.message(RegistrationStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()

    if not city or len(city) > 60:
        await message.answer("Please enter a valid city name.")
        return

    if not await _update_user(message.from_user.id, {"city": city}):
        await message.answer("⚠️ Couldn't save your city. Please try again.")
        return

    await state.set_state(RegistrationStates.waiting_for_bio)
    await message.answer("Tell us a little about yourself (a short bio, max 300 characters):")


@router.message(RegistrationStates.waiting_for_bio)
async def process_bio(message: Message, state: FSMContext) -> None:
    bio = (message.text or "").strip()

    if not bio or len(bio) > 300:
        await message.answer("Bio must be between 1 and 300 characters. Try again.")
        return

    if not await _update_user(message.from_user.id, {"bio": bio}):
        await message.answer("⚠️ Couldn't save your bio. Please try again.")
        return

    await state.set_state(RegistrationStates.waiting_for_photo)
    await message.answer(
        "📷 Send a profile photo, or skip this step.",
        reply_markup=skip_photo_kb(),
    )


@router.message(RegistrationStates.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext) -> None:
    photo_file_id = message.photo[-1].file_id

    if not await _update_user(
        message.from_user.id,
        {"photo_file_id": photo_file_id, "status": UserStatus.ACTIVE.value},
    ):
        await message.answer("⚠️ Couldn't save your photo. Please try again.")
        return

    await state.clear()
    await message.answer(
        "🎉 Your profile is complete! You can now search for matches.",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(RegistrationStates.waiting_for_photo, F.data == "profile:skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _update_user(callback.from_user.id, {"status": UserStatus.ACTIVE.value}):
        await callback.answer("⚠️ Couldn't proceed. Try again.", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text("🎉 Your profile is complete!")
    await callback.message.answer("You can now search for matches.", reply_markup=main_menu_kb())
    await callback.answer()


# ---------------------------------------------------------------------------
# Profile viewing & editing
# ---------------------------------------------------------------------------

@router.message(F.text == "👤 My profile")
async def show_profile(message: Message) -> None:
    db = get_db()

    try:
        doc = await db["users"].find_one({"telegram_id": message.from_user.id})
    except PyMongoError as exc:
        logger.error("DB error fetching profile for %s: %s", message.from_user.id, exc)
        await message.answer("⚠️ Couldn't load your profile right now.")
        return

    if doc is None:
        await message.answer("No profile found. Use /start to create one.")
        return

    try:
        profile = UserProfile.from_mongo(doc)
    except Exception as exc:
        logger.error("Corrupt profile for %s: %s", message.from_user.id, exc)
        await message.answer("⚠️ Your profile data seems corrupted.")
        return

    text = (
        f"👤 <b>{profile.name}</b>, {profile.age}\n"
        f"🚻 {profile.gender.value if profile.gender else '—'}\n"
        f"💘 Looking for: {profile.looking_for.value if profile.looking_for else '—'}\n"
        f"🏙 {profile.city or '—'}\n"
        f"📝 {profile.bio or '—'}"
    )

    if profile.photo_file_id:
        await message.answer_photo(profile.photo_file_id, caption=text)
    else:
        await message.answer(text)

    await message.answer("Edit your profile below:", reply_markup=edit_profile_kb())


@router.callback_query(F.data.startswith("edit:"))
async def start_edit(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":", 1)[1]

    if field == "cancel":
        await state.clear()
        await callback.message.edit_text("Edit cancelled.")
        await callback.answer()
        return

    prompts = {
        "name": ("Enter your new name:", EditProfileStates.editing_name),
        "age": ("Enter your new age:", EditProfileStates.editing_age),
        "city": ("Enter your new city:", EditProfileStates.editing_city),
        "bio": ("Enter your new bio (max 300 characters):", EditProfileStates.editing_bio),
        "photo": ("Send your new profile photo:", EditProfileStates.editing_photo),
    }

    if field == "gender":
        await callback.message.edit_text("Choose your new gender:")
        await callback.message.answer("Select:", reply_markup=gender_selection_kb())
        await state.set_state(EditProfileStates.editing_gender)
        await callback.answer()
        return

    if field == "looking_for":
        await callback.message.edit_text("Choose who you're looking for:")
        await callback.message.answer("Select:", reply_markup=looking_for_kb())
        await state.set_state(EditProfileStates.editing_looking_for)
        await callback.answer()
        return

    if field not in prompts:
        await callback.answer("Unknown field.", show_alert=True)
        return

    prompt_text, target_state = prompts[field]
    await state.set_state(target_state)
    await callback.message.edit_text(prompt_text)
    await callback.message.answer("You can cancel anytime:", reply_markup=cancel_edit_kb())
    await callback.answer()


@router.callback_query(F.data == "edit:cancel")
async def cancel_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Edit cancelled.")
    await callback.answer()


@router.message(EditProfileStates.editing_name)
async def edit_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 50:
        await message.answer("Please enter a valid name.")
        return
    await _update_user(message.from_user.id, {"name": name})
    await state.clear()
    await message.answer("✅ Name updated!", reply_markup=main_menu_kb())


@router.message(EditProfileStates.editing_age)
async def edit_age(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or not (settings.MIN_AGE <= int(text) <= settings.MAX_AGE):
        await message.answer(f"Enter a valid age ({settings.MIN_AGE}-{settings.MAX_AGE}).")
        return
    await _update_user(message.from_user.id, {"age": int(text)})
    await state.clear()
    await message.answer("✅ Age updated!", reply_markup=main_menu_kb())


@router.callback_query(EditProfileStates.editing_gender, F.data.startswith("gender:"))
async def edit_gender(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        gender = Gender(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid selection.", show_alert=True)
        return
    await _update_user(callback.from_user.id, {"gender": gender.value})
    await state.clear()
    await callback.message.edit_text("✅ Gender updated!")
    await callback.answer()


@router.callback_query(EditProfileStates.editing_looking_for, F.data.startswith("looking_for:"))
async def edit_looking_for(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        looking_for = LookingFor(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid selection.", show_alert=True)
        return
    await _update_user(callback.from_user.id, {"looking_for": looking_for.value})
    await state.clear()
    await callback.message.edit_text("✅ Preference updated!")
    await callback.answer()


@router.message(EditProfileStates.editing_city)
async def edit_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()
    if not city or len(city) > 60:
        await message.answer("Please enter a valid city name.")
        return
    await _update_user(message.from_user.id, {"city": city})
    await state.clear()
    await message.answer("✅ City updated!", reply_markup=main_menu_kb())


@router.message(EditProfileStates.editing_bio)
async def edit_bio(message: Message, state: FSMContext) -> None:
    bio = (message.text or "").strip()
    if not bio or len(bio) > 300:
        await message.answer("Bio must be 1-300 characters.")
        return
    await _update_user(message.from_user.id, {"bio": bio})
    await state.clear()
    await message.answer("✅ Bio updated!", reply_markup=main_menu_kb())


@router.message(EditProfileStates.editing_photo, F.photo)
async def edit_photo(message: Message, state: FSMContext) -> None:
    photo_file_id = message.photo[-1].file_id
    await _update_user(message.from_user.id, {"photo_file_id": photo_file_id})
    await state.clear()
    await message.answer("✅ Photo updated!", reply_markup=main_menu_kb())
