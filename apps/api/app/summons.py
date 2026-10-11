"""Server-owned summon pool, Aether spending, and collection effects."""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .config import settings
from .contracts import SummonCategory, SummonContent, SummonRarity
from .economy import InsufficientAether, refund_aether, spend_aether

POOL_PATH = Path(__file__).with_name("summon_pool.json")
RARITIES = [SummonRarity.R, SummonRarity.SR, SummonRarity.SSR, SummonRarity.UR]
ALLOWED_STATS = {"str", "agi", "int", "vit", "lck"}


class SummonConfigurationError(Exception):
    pass


def _json_setting(raw: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SummonConfigurationError(f"{label} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise SummonConfigurationError(f"{label} must be a JSON object")
    return parsed


def summon_rates() -> dict[str, float]:
    raw = _json_setting(settings.summon_rates, "SUMMON_RATES")
    if set(raw) != {rarity.value for rarity in RARITIES}:
        raise SummonConfigurationError("SUMMON_RATES must define R, SR, SSR, and UR")
    try:
        if any(isinstance(value, bool) for value in raw.values()):
            raise ValueError("boolean rate")
        rates = {key: float(raw[key]) for key in raw}
    except (TypeError, ValueError) as exc:
        raise SummonConfigurationError("Summon rates must be numeric") from exc
    if any(not math.isfinite(rate) or rate < 0 for rate in rates.values()) or abs(sum(rates.values()) - 100) > 0.0001:
        raise SummonConfigurationError("Summon rates must be non-negative and total 100")
    return rates


def duplicate_refunds() -> dict[str, int]:
    raw = _json_setting(settings.summon_duplicate_refunds, "SUMMON_DUPLICATE_REFUNDS")
    if set(raw) != {rarity.value for rarity in RARITIES}:
        raise SummonConfigurationError("SUMMON_DUPLICATE_REFUNDS must define R, SR, SSR, and UR")
    refunds: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SummonConfigurationError("Duplicate refunds must be non-negative integers")
        refunds[key] = value
    return refunds


def get_summon_pool() -> dict[str, Any]:
    try:
        raw_pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
        pool = [SummonContent.model_validate(item).model_dump(mode="json") for item in raw_pool]
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SummonConfigurationError("Summon content pool is invalid") from exc
    rates = summon_rates()
    duplicate_aether = duplicate_refunds()
    if len({item["id"] for item in pool}) != len(pool):
        raise SummonConfigurationError("Summon content IDs must be unique")
    for item in pool:
        effect = item["effect"]
        kind = effect.get("kind")
        if kind == "quest_modifier" and isinstance(effect.get("cue"), str) and effect["cue"]:
            continue
        if kind == "title_unlock" and isinstance(effect.get("title"), str) and effect["title"]:
            continue
        if (kind == "stat_bonus" and effect.get("stat") in ALLOWED_STATS
                and isinstance(effect.get("amount"), int) and not isinstance(effect.get("amount"), bool)
                and effect["amount"] >= 1):
            continue
        raise SummonConfigurationError(f"Summon effect is invalid for {item['id']}")
    if settings.summon_cost <= 0:
        raise SummonConfigurationError("SUMMON_COST must be positive")
    for rarity in RARITIES:
        if rates[rarity.value] > 0 and not any(item["rarity"] == rarity.value for item in pool):
            raise SummonConfigurationError(f"No summon content configured for {rarity.value}")
    return {"cost": settings.summon_cost, "rates": rates,
            "duplicate_refunds": duplicate_aether, "categories": [item.value for item in SummonCategory],
            "pool": pool}


def _draw_content(pool: dict[str, Any]) -> dict[str, Any]:
    rates = pool["rates"]
    roll = random.SystemRandom().random() * 100
    selected_rarity = RARITIES[-1].value
    for rarity in RARITIES:
        roll -= rates[rarity.value]
        if roll < 0:
            selected_rarity = rarity.value
            break
    choices = [item for item in pool["pool"] if item["rarity"] == selected_rarity]
    return random.SystemRandom().choice(choices)


async def _apply_effect(database: Any, player_id: str, attempt_id: str, content: dict[str, Any]) -> None:
    effect = content.get("effect", {})
    kind = effect.get("kind")
    update: dict[str, Any] = {"$addToSet": {"applied_summon_effect_ids": attempt_id}}
    if kind == "quest_modifier":
        cue = effect.get("cue")
        if not isinstance(cue, str) or not cue:
            raise SummonConfigurationError("Quest modifier has no cue")
        update["$addToSet"]["unlocks.quest_modifiers"] = cue
    elif kind == "title_unlock":
        title = effect.get("title")
        if not isinstance(title, str) or not title:
            raise SummonConfigurationError("Title unlock has no title")
        update["$addToSet"]["unlocks.titles"] = title
    elif kind == "stat_bonus":
        stat, amount = effect.get("stat"), effect.get("amount")
        if stat not in ALLOWED_STATS or isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
            raise SummonConfigurationError("Stat bonus is invalid")
        update["$inc"] = {f"stats.{stat}": amount}
    else:
        raise SummonConfigurationError("Summon effect type is unsupported")
    await database.players.update_one({"id": player_id, "applied_summon_effect_ids": {"$ne": attempt_id}}, update)


async def perform_summon(database: Any, player_id: str, request_id: str) -> dict[str, Any]:
    pool = get_summon_pool()
    player = await database.players.find_one({"id": player_id})
    if player is None:
        raise LookupError("Player not found")

    attempt_id = f"{player_id}:{request_id}"
    attempt = await database.summon_attempts.find_one({"_id": attempt_id})
    if attempt is None:
        content = _draw_content(pool)
        attempt = {"_id": attempt_id, "id": attempt_id, "player_id": player_id,
                   "request_id": request_id, "status": "pending", "content": content,
                   "cost": pool["cost"], "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            await database.summon_attempts.insert_one(attempt)
        except DuplicateKeyError:
            attempt = await database.summon_attempts.find_one({"_id": attempt_id})
    if attempt["status"] == "completed":
        attempt.pop("_id", None)
        return attempt["result"]
    if attempt["status"] == "rejected":
        raise InsufficientAether("Not enough Aether to summon")

    cost = int(attempt["cost"])
    try:
        await spend_aether(database, player_id, f"summon-spend:{attempt_id}", cost, attempt_id)
    except InsufficientAether:
        await database.summon_attempts.update_one({"_id": attempt_id}, {"$set": {"status": "rejected"}})
        raise

    content = attempt["content"]
    inventory_id = f"{player_id}:{content['id']}"
    inventory = {"_id": inventory_id, "id": inventory_id, "player_id": player_id,
                 "entity_id": content["id"], "content": content, "count": 0,
                 "first_attempt_id": attempt_id, "acquired_at": datetime.now(timezone.utc).isoformat(),
                 "summon_attempt_ids": []}
    try:
        await database.summons.insert_one(inventory)
    except DuplicateKeyError:
        pass
    await database.summons.find_one_and_update(
        {"_id": inventory_id, "summon_attempt_ids": {"$ne": attempt_id}},
        {"$inc": {"count": 1}, "$addToSet": {"summon_attempt_ids": attempt_id},
         "$set": {"last_acquired_at": datetime.now(timezone.utc).isoformat()}},
        return_document=ReturnDocument.BEFORE,
    )
    item = await database.summons.find_one({"_id": inventory_id})
    if item is None:
        raise RuntimeError("Summon inventory could not be recorded")
    duplicate = item.get("first_attempt_id") != attempt_id

    if not duplicate:
        await _apply_effect(database, player_id, attempt_id, content)
    refund = duplicate_refunds()[content["rarity"]] if duplicate else 0
    if refund:
        await refund_aether(database, player_id, f"summon-duplicate-refund:{attempt_id}", refund, content["id"])
    player = await database.players.find_one({"id": player_id})
    result = {"attempt_id": attempt_id, "content": content, "duplicate": duplicate,
              "duplicate_refund": refund, "cost": cost, "aether_balance": int(player.get("aether", 0)),
              "collection_count": int(item.get("count", 1))}
    await database.summon_attempts.update_one({"_id": attempt_id}, {"$set": {"status": "completed", "result": result}})
    return result


async def get_collection(database: Any, player_id: str) -> list[dict[str, Any]]:
    return await database.summons.find({"player_id": player_id}, {"_id": 0}).sort("content.rarity", 1).to_list(length=500)
