"""
keyboards/profile_kb.py
Inline keyboards used during profile creation and editing.
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Gender, LookingFor


def gender_selection_kb() -> InlineKeyboardMarkup:
    """Keyboard for choosing the user's own gender."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👨 Male", callback_data=f"gender:{Gender.MALE.value}")
    builder.button(text="👩 Female", callback_data=f"gender:{Gender.FEMALE.value}")
    builder.button(text="🌈 Other", callback_data=f"gender:{Gender.OTHER.value}")
    builder.adjust(2, 1)
    return builder.as_markup()


def looking_for_kb() -> InlineKeyboardMarkup:
    """Keyboard for choosing preferred match gender."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👨 Men", callback_data=f"looking_for:{LookingFor.MALE.value}")
    builder.button(text="👩 Women", callback_data=f"looking_for:{LookingFor.FEMALE.value}")
    builder.button(text="🌍 Anyone", callback_data=f"looking_for:{LookingFor.ANY.value}")
    builder.adjust(2, 1)
    return builder.as_markup()


def skip_photo_kb() -> InlineKeyboardMarkup:
    """Allows skipping the optional profile photo step."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Skip photo", callback_data="profile:skip_photo")
    return builder.as_markup()


def edit_profile_kb() -> InlineKeyboardMarkup:
    """Menu for editing individual profile fields."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Name", callback_data="edit:name")
    builder.button(text="🎂 Age", callback_data="edit:age")
    builder.button(text="🚻 Gender", callback_data="edit:gender")
    builder.button(text="💘 Looking for", callback_data="edit:looking_for")
    builder.button(text="🏙 City", callback_data="edit:city")
    builder.button(text="📝 Bio", callback_data="edit:bio")
    builder.button(text="📷 Photo", callback_data="edit:photo")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def cancel_edit_kb() -> InlineKeyboardMarkup:
    """Cancel button shown while editing a single field."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data="edit:cancel")
    return builder.as_markup()
