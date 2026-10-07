from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class Rarity(StrEnum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class VerificationMethod(StrEnum):
    SELF_REPORTED = "self_reported"
    AI_REVIEW = "ai_review"
    SERVER_VALIDATED = "server_validated"
    HUMAN_REVIEW = "human_review"


class QuestStatus(StrEnum):
    DRAFT = "draft"
    AVAILABLE = "available"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class Archetype(StrEnum):
    EXPLORER = "explorer"
    OBSERVER = "observer"
    SEEKER = "seeker"
    WANDERER = "wanderer"


class PlayerStats(BaseModel):
    str: int = Field(default=5, ge=0)
    agi: int = Field(default=5, ge=0)
    int: int = Field(default=5, ge=0)
    vit: int = Field(default=5, ge=0)
    lck: int = Field(default=5, ge=0)


class PlayerPreferences(BaseModel):
    interests: str = Field(default="", max_length=500)
    quest_duration_minutes: int = Field(default=30, ge=5, le=240)


class APIError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None


class APIResponse(BaseModel):
    data: Any | None = None
    error: APIError | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class Player(BaseModel):
    id: str
    display_name: str
    created_at: datetime
    archetype: Archetype = Archetype.EXPLORER
    level: int = Field(default=1, ge=1)
    experience: int = Field(default=0, ge=0)
    experience_to_next_level: int = 100
    aether: int = Field(default=0, ge=0)
    stats: PlayerStats = Field(default_factory=PlayerStats)
    preferences: PlayerPreferences = Field(default_factory=PlayerPreferences)
    progress: Progress | None = None

    model_config = ConfigDict(extra="ignore")


class PlayerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=32)
    archetype: Archetype
    preferences: PlayerPreferences = Field(default_factory=PlayerPreferences)


class PlayerProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=32)
    archetype: Archetype | None = None
    preferences: PlayerPreferences | None = None


class Objective(BaseModel):
    id: str
    description: str
    optional: bool = False
    verification: VerificationMethod = VerificationMethod.SELF_REPORTED


class Reward(BaseModel):
    id: str
    kind: str
    quantity: int = Field(ge=1)
    rarity: Rarity = Rarity.COMMON
    description: str | None = None


class Quest(BaseModel):
    id: str
    title: str
    description: str
    objectives: list[Objective]
    rewards: list[Reward] = Field(default_factory=list)
    status: QuestStatus = QuestStatus.AVAILABLE
    level: int = Field(default=1, ge=1)


class QuestAttempt(BaseModel):
    id: str
    player_id: str
    quest_id: str
    status: QuestStatus = QuestStatus.ACTIVE
    started_at: datetime
    completed_at: datetime | None = None
    objective_progress: dict[str, bool] = Field(default_factory=dict)


class InventoryItem(BaseModel):
    id: str
    item_id: str
    quantity: int = Field(ge=0)
    rarity: Rarity = Rarity.COMMON


class Summon(BaseModel):
    id: str
    player_id: str
    entity_id: str
    acquired_at: datetime
    rarity: Rarity


class Discovery(BaseModel):
    id: str
    player_id: str
    subject_id: str
    discovered_at: datetime


class Progress(BaseModel):
    level: int = Field(default=1, ge=1)
    experience: int = Field(default=0, ge=0)
    completed_quest_ids: list[str] = Field(default_factory=list)


class NPC(BaseModel):
    id: str
    name: str
    description: str
    location_id: str | None = None


class WorldEvent(BaseModel):
    id: str
    title: str
    description: str
    starts_at: datetime
    ends_at: datetime | None = None


class AIQuestOutput(BaseModel):
    """Constrained JSON contract for quests proposed by the Game Master model."""
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    objectives: list[Objective] = Field(min_length=1, max_length=10)
    rewards: list[Reward] = Field(default_factory=list, max_length=5)
    level: int = Field(default=1, ge=1, le=100)
