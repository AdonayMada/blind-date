"""
utils/states.py
FSM state groups used across the bot's conversation flows.
"""

from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """States for the initial profile creation flow (triggered by /start)."""

    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_looking_for = State()
    waiting_for_city = State()
    waiting_for_bio = State()
    waiting_for_photo = State()


class EditProfileStates(StatesGroup):
    """States for editing individual fields of an existing profile."""

    editing_name = State()
    editing_age = State()
    editing_gender = State()
    editing_looking_for = State()
    editing_city = State()
    editing_bio = State()
    editing_photo = State()