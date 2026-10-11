"""Audited Aether credits and debits. Summon costs must be chosen server-side."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .contracts import AetherTransactionType

QUEST_COMPLETE_AETHER = 30


class InsufficientAether(Exception):
    pass


class AetherLedgerError(Exception):
    pass


async def apply_aether_transaction(database: Any, player_id: str, transaction_id: str,
                                   transaction_type: AetherTransactionType, amount: int,
                                   source_id: str | None = None) -> dict[str, Any]:
    if amount <= 0:
        raise ValueError("Aether transaction amount must be positive")
    entry = {
        "_id": transaction_id, "id": transaction_id, "player_id": player_id,
        "transaction_type": transaction_type.value, "amount": amount,
        "source_id": source_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending", "balance_before": None, "balance_after": None,
    }
    try:
        await database.aether_ledger.insert_one(entry)
    except DuplicateKeyError:
        existing = await database.aether_ledger.find_one({"_id": transaction_id})
        if not existing:
            raise
        if (existing["player_id"], existing["transaction_type"], existing["amount"]) != (player_id, transaction_type.value, amount):
            raise AetherLedgerError("Transaction ID was already used for a different Aether operation")
        if existing["status"] == "rejected":
            raise InsufficientAether("Not enough Aether for this operation")
        if existing["status"] == "applied":
            existing.pop("_id", None)
            existing["already_applied"] = True
            return existing

    delta = -amount if transaction_type == AetherTransactionType.AETHER_SPEND else amount
    query: dict[str, Any] = {"id": player_id, "aether_event_ids": {"$ne": transaction_id}}
    if delta < 0:
        query["aether"] = {"$gte": amount}
    before = await database.players.find_one_and_update(
        query,
        {"$inc": {"aether": delta}, "$addToSet": {"aether_event_ids": transaction_id}},
        return_document=ReturnDocument.BEFORE,
    )
    if before is None:
        player = await database.players.find_one({"id": player_id})
        if player is None:
            await database.aether_ledger.update_one({"_id": transaction_id}, {"$set": {"status": "rejected", "reason": "player_not_found"}})
            raise AetherLedgerError("Player not found")
        if transaction_id in player.get("aether_event_ids", []):
            after_balance = int(player.get("aether", 0))
            await database.aether_ledger.update_one({"_id": transaction_id}, {"$set": {"status": "applied", "balance_after": after_balance}})
            recovered = await database.aether_ledger.find_one({"_id": transaction_id})
            recovered.pop("_id", None)
            recovered["already_applied"] = True
            return recovered
        current = int(player.get("aether", 0))
        await database.aether_ledger.update_one({"_id": transaction_id}, {"$set": {
            "status": "rejected", "reason": "insufficient_aether",
            "balance_before": current, "balance_after": current,
        }})
        raise InsufficientAether("Not enough Aether for this operation")

    balance_before = int(before.get("aether", 0))
    balance_after = balance_before + delta
    await database.aether_ledger.update_one({"_id": transaction_id}, {"$set": {
        "status": "applied", "balance_before": balance_before, "balance_after": balance_after,
    }})
    entry.update({"status": "applied", "balance_before": balance_before, "balance_after": balance_after})
    entry.pop("_id", None)
    return entry


async def earn_aether(database: Any, player_id: str, transaction_id: str, amount: int,
                      source_id: str | None = None) -> dict[str, Any]:
    return await apply_aether_transaction(database, player_id, transaction_id,
                                          AetherTransactionType.AETHER_EARN, amount, source_id)


async def spend_aether(database: Any, player_id: str, transaction_id: str, amount: int,
                       source_id: str | None = None) -> dict[str, Any]:
    """Debit at a cost supplied by trusted server code, never a client payload."""
    return await apply_aether_transaction(database, player_id, transaction_id,
                                          AetherTransactionType.AETHER_SPEND, amount, source_id)


async def refund_aether(database: Any, player_id: str, transaction_id: str, amount: int,
                        source_id: str | None = None) -> dict[str, Any]:
    return await apply_aether_transaction(database, player_id, transaction_id,
                                          AetherTransactionType.AETHER_REFUND, amount, source_id)
