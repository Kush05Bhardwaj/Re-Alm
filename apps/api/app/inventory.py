"""Player inventory and collection discovery views over server-owned content."""
from __future__ import annotations

from typing import Any

from .contracts import CollectionProgress, SummonRarity
from .summons import get_summon_pool


def _effect_description(effect: dict[str, Any]) -> str:
    kind = effect.get("kind")
    if kind == "quest_modifier":
        return str(effect.get("cue", "Unlocks future quest content."))
    if kind == "stat_bonus":
        return f"Permanently increases {str(effect.get('stat', 'player stat')).upper()} by {effect.get('amount', 1)}."
    if kind == "title_unlock":
        return f"Unlocks the {effect.get('title', 'new')} title."
    return "Adventure content added to your collection."


def _inventory_entry(content: dict[str, Any], owned: dict[str, Any] | None, summon_cost: int) -> dict[str, Any]:
    unlocked = owned is not None
    effect = content.get("effect", {})
    return {
        "id": content["id"],
        "name": content["name"],
        "rarity": content["rarity"],
        "type": content["category"],
        "description": content["description"],
        "how_obtained": "Summoned with Aether" if unlocked else f"Summon for {summon_cost} Aether",
        "effect": {**effect, "summary": _effect_description(effect)},
        "unlocked": unlocked,
        "count": int(owned.get("count", 0)) if owned else 0,
        "acquired_at": owned.get("acquired_at") if owned else None,
    }


async def list_inventory(database: Any, player_id: str) -> list[dict[str, Any]]:
    pool = get_summon_pool()
    records = await database.summons.find({"player_id": player_id}, {"_id": 0}).to_list(length=500)
    owned_by_id = {record["entity_id"]: record for record in records}
    entries = [_inventory_entry(content, owned_by_id.get(content["id"]), pool["cost"])
               for content in pool["pool"]]
    order = {rarity.value: index for index, rarity in enumerate(SummonRarity)}
    return sorted(entries, key=lambda item: (item["type"], order[item["rarity"]], item["name"]))


async def get_inventory_item(database: Any, player_id: str, item_id: str) -> dict[str, Any] | None:
    pool = get_summon_pool()
    content = next((item for item in pool["pool"] if item["id"] == item_id), None)
    if content is None:
        return None
    owned = await database.summons.find_one({"player_id": player_id, "entity_id": item_id}, {"_id": 0})
    return _inventory_entry(content, owned, pool["cost"])


async def get_collection_progress(database: Any, player: dict[str, Any]) -> dict[str, Any]:
    player_id = player["id"]
    pool = get_summon_pool()["pool"]
    records = await database.summons.find({"player_id": player_id}, {"_id": 0, "entity_id": 1, "content.rarity": 1, "content.category": 1}).to_list(length=500)
    discovered_ids = {record["entity_id"] for record in records}
    discovered_content = {item["id"]: item for item in pool if item["id"] in discovered_ids}
    rarity_available = {rarity.value: sum(item["rarity"] == rarity.value for item in pool) for rarity in SummonRarity}
    rarity_discovered = {rarity.value: sum(item["rarity"] == rarity.value for item in discovered_content.values()) for rarity in SummonRarity}
    quest_types = await database.quests.distinct("category", {"player_id": player_id, "status": "completed"})
    titles = sorted(set((player.get("unlocks") or {}).get("titles", [])))
    return CollectionProgress(
        total_discovered=len(discovered_content),
        total_available=len(pool),
        rarity_discovered=rarity_discovered,
        rarity_available=rarity_available,
        quest_types_discovered=sorted(set(quest_types)),
        npcs_discovered=sum(item["category"] == "NPC" for item in discovered_content.values()),
        titles_unlocked=titles,
    ).model_dump(mode="json")
