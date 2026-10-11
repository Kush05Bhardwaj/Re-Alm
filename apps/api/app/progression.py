"""XP rewards and level progression. Event IDs make awards safe to retry."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from .contracts import ProgressionEventType


XP_REWARDS = {
    ProgressionEventType.OBJECTIVE_COMPLETE: 20,
    ProgressionEventType.QUEST_COMPLETE: 100,
    ProgressionEventType.BONUS_OBJECTIVE: 25,
    ProgressionEventType.RARE_DISCOVERY: 50,
}
STAT_NAMES = ("str", "agi", "int", "vit", "lck")


def calculate_next_level_xp(level: int) -> int:
    return 100 * max(1, level)


def check_level_up(level: int, experience: int) -> tuple[int, int, int]:
    """Return final level, carried XP, and number of levels gained."""
    levels_gained = 0
    while experience >= calculate_next_level_xp(level):
        experience -= calculate_next_level_xp(level)
        level += 1
        levels_gained += 1
    return level, experience, levels_gained


async def add_xp(database: Any, player_id: str, event_id: str,
                 event_type: ProgressionEventType, source_id: str | None = None) -> dict[str, Any]:
    """Apply one idempotent XP event and return its recorded level/stat changes."""
    amount = XP_REWARDS[event_type]
    created_at = datetime.now(timezone.utc)
    event = {
        "_id": event_id, "id": event_id, "player_id": player_id,
        "event_type": event_type.value, "xp": amount,
        "source_id": source_id, "created_at": created_at.isoformat(),
        "level_before": 1, "level_after": 1, "stat_increases": {},
    }
    try:
        await database.progression_events.insert_one(event)
    except DuplicateKeyError:
        existing = await database.progression_events.find_one({"_id": event_id})
        if existing and existing.get("error"):
            await database.progression_events.delete_one({"_id": event_id, "error": existing["error"]})
            return await add_xp(database, player_id, event_id, event_type, source_id)
        if existing:
            existing.pop("_id", None)
            existing["already_awarded"] = True
            return existing
        raise

    for _ in range(12):
        player = await database.players.find_one({"id": player_id})
        if player is None:
            await database.progression_events.delete_one({"_id": event_id})
            raise ValueError("Player not found")
        level = max(1, int(player.get("level", 1)))
        experience = max(0, int(player.get("experience", 0)))
        next_level, remainder, levels_gained = check_level_up(level, experience + amount)
        stat_increases: dict[str, int] = {}
        stats = dict(player.get("stats", {}))
        for _ in range(levels_gained):
            name = random.choice(STAT_NAMES)
            stats[name] = int(stats.get(name, 5)) + 1
            stat_increases[name] = stat_increases.get(name, 0) + 1
        completed_ids = list((player.get("progress") or {}).get("completed_quest_ids", []))
        update = await database.players.update_one(
            {"id": player_id, "level": player.get("level", 1), "experience": player.get("experience", 0)},
            {"$set": {
                "level": next_level, "experience": remainder,
                "experience_to_next_level": calculate_next_level_xp(next_level),
                "total_experience": int(player.get("total_experience", player.get("experience", 0))) + amount,
                "stats": stats,
                "progress": {"level": next_level, "experience": remainder, "completed_quest_ids": completed_ids},
            }},
        )
        if update.modified_count:
            event.update({"level_before": level, "level_after": next_level, "stat_increases": stat_increases})
            await database.progression_events.update_one({"_id": event_id}, {"$set": {key: value for key, value in event.items() if key != "_id"}})
            event.pop("_id", None)
            event["levels_gained"] = levels_gained
            event["experience_after"] = remainder
            return event

    # Preserve the event as unawarded so operators can see a contention failure instead of silently minting XP twice.
    await database.progression_events.update_one({"_id": event_id}, {"$set": {"error": "player update contention; retry required"}})
    raise RuntimeError("Progress update was busy; retry the reward event")


async def award_rare_discovery(database: Any, player_id: str, discovery_id: str) -> dict[str, Any]:
    """Award the rare-discovery event once when a trusted discovery flow records one."""
    return await add_xp(
        database, player_id, f"rare-discovery:{discovery_id}",
        ProgressionEventType.RARE_DISCOVERY, discovery_id,
    )
