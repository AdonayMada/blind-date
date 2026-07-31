"""
database/models.py
Pydantic data models representing MongoDB documents.

These models define the schema/shape of data stored in Mongo collections.
MongoDB itself is schemaless, but using pydantic gives us validation,
type safety, and easy serialization between the bot and the database.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class LookingFor(str, Enum):
    MALE = "male"
    FEMALE = "female"
    ANY = "any"


class UserStatus(str, Enum):
    NEW = "new"                # registering, profile incomplete
    ACTIVE = "active"          # profile complete, not searching
    SEARCHING = "searching"    # actively looking for a match
    IN_CHAT = "in_chat"        # currently paired with someone
    BANNED = "banned"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserProfile(BaseModel):
    """Represents a document in the 'users' collection."""

    telegram_id: int
    username: str | None = None
    first_name: str | None = None

    name: str | None = None
    age: int | None = None
    gender: Gender | None = None
    looking_for: LookingFor | None = None
    city: str | None = None
    bio: str | None = None
    photo_file_id: str | None = None

    status: UserStatus = UserStatus.NEW
    current_partner_id: int | None = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("age")
    @classmethod
    def validate_age(cls, v: int | None) -> int | None:
        if v is not None and (v < 16 or v > 100):
            raise ValueError("Age must be between 16 and 100.")
        return v

    def is_profile_complete(self) -> bool:
        """Checks whether all required fields for matching are filled in."""
        return all(
            [
                self.name,
                self.age is not None,
                self.gender is not None,
                self.looking_for is not None,
                self.city,
            ]
        )

    def to_mongo(self) -> dict:
        """Serializes the model into a Mongo-friendly dict."""
        data = self.model_dump(exclude={"telegram_id"})
        # Enums -> plain strings for storage
        for key in ("gender", "looking_for", "status"):
            if data.get(key) is not None:
                data[key] = data[key].value if hasattr(data[key], "value") else data[key]
        return data

    @classmethod
    def from_mongo(cls, doc: dict) -> "UserProfile":
        """Builds a UserProfile from a raw MongoDB document."""
        return cls(**doc)


class MatchRecord(BaseModel):
    """Represents a document in the 'matches' collection (match history)."""

    user_a_id: int
    user_b_id: int
    created_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    ended_reason: str | None = None  # "manual_stop", "reported", "timeout", etc.

    def to_mongo(self) -> dict:
        return self.model_dump()


class Report(BaseModel):
    """Represents a document in the 'reports' collection."""

    reporter_id: int
    reported_id: int
    reason: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)

    def to_mongo(self) -> dict:
        return self.model_dump()