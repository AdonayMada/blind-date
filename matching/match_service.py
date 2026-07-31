"""
matching/match_service.py
Core matchmaking logic: queueing users for search, finding compatible
partners, establishing chats, and tearing them down.

Design notes:
- The "search queue" is represented by users with status=SEARCHING in the
  'users' collection — no separate queue collection needed.
- Matching uses an atomic find_one_and_update to avoid race conditions
  where two concurrent searches could pair with the same candidate twice.
- Compatibility is based on mutual gender/looking_for preference.
"""

import logging
from datetime import datetime, timezone

from pymongo.errors import PyMongoError
from pymongo import ReturnDocument

from database.db import get_db
from database.models import LookingFor, MatchRecord, UserProfile, UserStatus

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_mutually_compatible(user: UserProfile, candidate: dict) -> bool:
    """
    Checks whether `user` and `candidate` (raw Mongo doc) are a mutual match
    based on gender and looking_for preferences.
    """
    candidate_gender = candidate.get("gender")
    candidate_looking_for = candidate.get("looking_for")

    if candidate_gender is None or candidate_looking_for is None:
        return False

    # Does the searching user's preference match the candidate's gender?
    user_wants_candidate = (
        user.looking_for == LookingFor.ANY or user.looking_for.value == candidate_gender
    )

    # Does the candidate's preference match the searching user's gender?
    candidate_wants_user = (
        candidate_looking_for == LookingFor.ANY.value or candidate_looking_for == user.gender.value
    )

    return user_wants_candidate and candidate_wants_user


async def find_match(telegram_id: int) -> int | None:
    """
    Attempts to find an immediate match for the given user.

    Returns:
        - The partner's telegram_id if a match was made immediately.
        - None if no match was found and the user was placed in the queue.

    Raises:
        RuntimeError if the user's profile cannot be loaded.
    """
    db = get_db()
    users = db["users"]

    try:
        user_doc = await users.find_one({"telegram_id": telegram_id})
    except PyMongoError as exc:
        logger.error("DB error loading user %s during matchmaking: %s", telegram_id, exc)
        raise

    if user_doc is None:
        raise RuntimeError(f"User {telegram_id} not found.")

    user = UserProfile.from_mongo(user_doc)

    # Mark this user as searching first (idempotent), so they're visible
    # to other concurrent searches even if we don't find anyone right now.
    try:
        await users.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"status": UserStatus.SEARCHING.value, "updated_at": _utcnow()}},
        )
    except PyMongoError as exc:
        logger.error("Failed to set SEARCHING status for %s: %s", telegram_id, exc)
        raise

    # Look for candidates: other users currently searching, excluding self.
    try:
        cursor = users.find(
            {
                "telegram_id": {"$ne": telegram_id},
                "status": UserStatus.SEARCHING.value,
            }
        )
        candidates = await cursor.to_list(length=200)
    except PyMongoError as exc:
        logger.error("DB error querying candidates for %s: %s", telegram_id, exc)
        raise

    for candidate in candidates:
        if not _is_mutually_compatible(user, candidate):
            continue

        partner_id = candidate["telegram_id"]

        # Atomically claim the candidate: only succeeds if they are STILL
        # searching (prevents double-matching under concurrency).
        try:
            claimed = await users.find_one_and_update(
                {"telegram_id": partner_id, "status": UserStatus.SEARCHING.value},
                {
                    "$set": {
                        "status": UserStatus.IN_CHAT.value,
                        "current_partner_id": telegram_id,
                        "updated_at": _utcnow(),
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            logger.error("DB error claiming candidate %s: %s", partner_id, exc)
            continue

        if claimed is None:
            # Someone else claimed this candidate first — try the next one.
            continue

        # Successfully claimed partner — now claim ourselves too.
        try:
            self_claimed = await users.find_one_and_update(
                {"telegram_id": telegram_id, "status": UserStatus.SEARCHING.value},
                {
                    "$set": {
                        "status": UserStatus.IN_CHAT.value,
                        "current_partner_id": partner_id,
                        "updated_at": _utcnow(),
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            logger.error("DB error self-claiming %s: %s", telegram_id, exc)
            # Roll back partner's claim since we couldn't complete the match.
            await users.update_one(
                {"telegram_id": partner_id},
                {"$set": {"status": UserStatus.SEARCHING.value, "current_partner_id": None}},
            )
            raise

        if self_claimed is None:
            # We were no longer searching (edge case) — roll back partner claim.
            logger.warning("Self-claim failed for %s; rolling back partner %s.", telegram_id, partner_id)
            await users.update_one(
                {"telegram_id": partner_id},
                {"$set": {"status": UserStatus.SEARCHING.value, "current_partner_id": None}},
            )
            return None

        # Record the match in history.
        try:
            match_record = MatchRecord(user_a_id=telegram_id, user_b_id=partner_id)
            await db["matches"].insert_one(match_record.to_mongo())
        except PyMongoError as exc:
            # Non-fatal — the chat is already established; just log it.
            logger.error("Failed to record match history for %s/%s: %s", telegram_id, partner_id, exc)

        logger.info("Matched users %s <-> %s", telegram_id, partner_id)
        return partner_id

    # No compatible candidate found — user remains in the search queue.
    return None


async def leave_search_queue(telegram_id: int) -> bool:
    """
    Removes a user from the search queue (sets status back to ACTIVE).

    Returns:
        True if the user was in the SEARCHING state and was removed.
        False if the user wasn't searching (no-op).
    """
    db = get_db()

    try:
        result = await db["users"].update_one(
            {"telegram_id": telegram_id, "status": UserStatus.SEARCHING.value},
            {"$set": {"status": UserStatus.ACTIVE.value, "updated_at": _utcnow()}},
        )
    except PyMongoError as exc:
        logger.error("DB error removing %s from search queue: %s", telegram_id, exc)
        raise

    return result.modified_count > 0


async def end_chat(telegram_id: int, reason: str = "manual_stop") -> int | None:
    """
    Ends the active chat for the given user (and implicitly for their
    partner, since both records are updated).

    Returns:
        The partner's telegram_id if a chat was ended, else None.
    """
    db = get_db()
    users = db["users"]

    try:
        user_doc = await users.find_one({"telegram_id": telegram_id})
    except PyMongoError as exc:
        logger.error("DB error loading user %s to end chat: %s", telegram_id, exc)
        raise

    if user_doc is None or user_doc.get("status") != UserStatus.IN_CHAT.value:
        return None

    partner_id = user_doc.get("current_partner_id")

    try:
        await users.update_one(
            {"telegram_id": telegram_id},
            {
                "$set": {
                    "status": UserStatus.ACTIVE.value,
                    "current_partner_id": None,
                    "updated_at": _utcnow(),
                }
            },
        )
        if partner_id:
            await users.update_one(
                {"telegram_id": partner_id},
                {
                    "$set": {
                        "status": UserStatus.ACTIVE.value,
                        "current_partner_id": None,
                        "updated_at": _utcnow(),
                    }
                },
            )
    except PyMongoError as exc:
        logger.error("DB error ending chat for %s/%s: %s", telegram_id, partner_id, exc)
        raise

    try:
        await db["matches"].update_one(
            {
                "$or": [
                    {"user_a_id": telegram_id, "user_b_id": partner_id},
                    {"user_a_id": partner_id, "user_b_id": telegram_id},
                ],
                "ended_at": None,
            },
            {"$set": {"ended_at": _utcnow(), "ended_reason": reason}},
            sort=[("created_at", -1)],
        )
    except PyMongoError as exc:
        # Non-fatal — chat state is already updated.
        logger.error("Failed to update match history for %s/%s: %s", telegram_id, partner_id, exc)

    logger.info("Chat ended between %s and %s (reason=%s)", telegram_id, partner_id, reason)
    return partner_id
