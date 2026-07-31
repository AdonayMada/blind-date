"""
keyboards/main_kb.py
Main menu keyboards (reply keyboard + core inline keyboards).
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Persistent bottom menu shown after profile setup."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🔍 Find a match"))
    builder.row(
        KeyboardButton(text="👤 My profile"),
        KeyboardButton(text="⚙️ Settings"),
    )
    builder.row(KeyboardButton(text="❓ Help"))
    return builder.as_markup(resize_keyboard=True)


def searching_kb() -> InlineKeyboardMarkup:
    """Shown while the user is searching for a match — allows cancel."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel search", callback_data="search:cancel")
    return builder.as_markup()


def in_chat_kb() -> InlineKeyboardMarkup:
    """Shown while the user is paired with a partner."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Next partner", callback_data="chat:next")
    builder.button(text="🛑 Stop chat", callback_data="chat:stop")
    builder.button(text="🚩 Report", callback_data="chat:report")
    builder.adjust(2, 1)
    return builder.as_markup()


def confirm_kb(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    """Generic yes/no confirmation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Yes", callback_data=yes_data)
    builder.button(text="❌ No", callback_data=no_data)
    builder.adjust(2)
    return builder.as_markup()


def back_kb(callback_data: str = "nav:back") -> InlineKeyboardMarkup:
    """Simple single 'back' button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back", callback_data=callback_data)]]
    )
