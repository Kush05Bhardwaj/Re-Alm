from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings
from .contracts import (
    APIResponse,
    Player,
    PlayerCreate,
    PlayerProfilePatch,
    Quest,
    QuestGenerationContext,
    QuestGenerationRequest,
    QuestStatus,
    ProgressionEventType,
    AetherTransaction,
    SummonRequest,
)
from .game_master import QuestGenerationError, generate_quest
from .economy import InsufficientAether, QUEST_COMPLETE_AETHER, earn_aether
from .progression import add_xp, calculate_next_level_xp
from .verification import SelfVerification, VisionVerification
from .summons import SummonConfigurationError, get_collection, get_summon_pool, perform_summon


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=2500)
    app.state.mongo_client = client
    app.state.database = client[settings.mongodb_database]
    try:
        yield
    finally:
        client.close()


app = FastAPI(title="RE API", version="0.1.0", openapi_url="/api/v1/openapi.json", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize_player(document: dict) -> Player:
    document.pop("_id", None)
    return Player.model_validate(document)


@app.post("/api/player/create", response_model=APIResponse, status_code=201, tags=["player"])
@app.post("/api/v1/player/create", response_model=APIResponse, status_code=201, tags=["player"], include_in_schema=False)
async def create_player(payload: PlayerCreate) -> APIResponse:
    player = Player(
        id=str(uuid4()),
        display_name=payload.display_name.strip(),
        created_at=datetime.now(timezone.utc),
        archetype=payload.archetype,
        preferences=payload.preferences,
    )
    if not player.display_name:
        raise HTTPException(status_code=422, detail="Player name cannot be blank")
    await app.state.database.players.insert_one(player.model_dump(mode="json"))
    return APIResponse(data=player)


@app.get("/api/player/me", response_model=APIResponse, tags=["player"])
@app.get("/api/v1/player/me", response_model=APIResponse, tags=["player"], include_in_schema=False)
async def get_current_player(x_player_id: str = Header(..., alias="X-Player-ID")) -> APIResponse:
    document = await app.state.database.players.find_one({"id": x_player_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return APIResponse(data=serialize_player(document))


@app.patch("/api/player/profile", response_model=APIResponse, tags=["player"])
@app.patch("/api/v1/player/profile", response_model=APIResponse, tags=["player"], include_in_schema=False)
async def update_player_profile(
    payload: PlayerProfilePatch,
    x_player_id: str = Header(..., alias="X-Player-ID"),
) -> APIResponse:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True, mode="json")
    if not changes:
        raise HTTPException(status_code=400, detail="No profile fields provided")
    result = await app.state.database.players.update_one({"id": x_player_id}, {"$set": changes})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Player not found")
    document = await app.state.database.players.find_one({"id": x_player_id})
    return APIResponse(data=serialize_player(document))


@app.post("/api/quest/generate", response_model=APIResponse, status_code=201, tags=["quest"])
@app.post("/api/v1/quest/generate", response_model=APIResponse, status_code=201, tags=["quest"], include_in_schema=False)
async def create_quest(
    payload: QuestGenerationRequest,
    x_player_id: str = Header(..., alias="X-Player-ID"),
) -> APIResponse:
    player_document = await app.state.database.players.find_one({"id": x_player_id})
    if player_document is None:
        raise HTTPException(status_code=404, detail="Player not found")
    player = Player.model_validate({key: value for key, value in player_document.items() if key != "_id"})

    history_documents = await app.state.database.quests.find({"player_id": x_player_id}).sort("created_at", -1).limit(12).to_list(length=12)
    history = [
        {key: value for key, value in item.items() if key in {"title", "category", "description", "objectives"}}
        for item in history_documents
    ]
    discovery_documents = await app.state.database.discoveries.find({"player_id": x_player_id}).sort("discovered_at", -1).limit(20).to_list(length=20)
    discoveries = [
        {key: value for key, value in item.items() if key == "subject_id"}
        for item in discovery_documents
    ]
    context = QuestGenerationContext(
        player={
            "display_name": player.display_name,
            "level": player.level,
            "archetype": player.archetype.value,
            "interests": player.preferences.interests,
        },
        history=history,
        available_minutes=player.preferences.quest_duration_minutes,
        environment=payload.environment,
        progression={
            "level": player.level,
            "experience": player.experience,
            "experience_to_next_level": player.experience_to_next_level,
            "completed_quests": sum(1 for item in history_documents if item.get("status") == QuestStatus.COMPLETED.value),
        },
        discoveries=discoveries,
        collection_effects=player.unlocks.quest_modifiers,
    )
    try:
        proposal = await generate_quest(context)
    except QuestGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    quest = Quest(
        id=str(uuid4()),
        player_id=x_player_id,
        title=proposal.title,
        description=proposal.description,
        category=proposal.category,
        difficulty=proposal.difficulty,
        estimated_minutes=proposal.estimated_minutes,
        objectives=[objective.model_copy(update={"id": str(uuid4())}) for objective in proposal.objectives],
        verification=proposal.verification,
        xp_reward=proposal.xp_reward,
        aether_reward=QUEST_COMPLETE_AETHER,
        status=QuestStatus.AVAILABLE,
        level=player.level,
        created_at=datetime.now(timezone.utc),
    )
    await app.state.database.quests.insert_one(quest.model_dump(mode="json"))
    return APIResponse(data=quest)


@app.get("/api/summon/pool", response_model=APIResponse, tags=["summon"])
@app.get("/api/v1/summon/pool", response_model=APIResponse, tags=["summon"], include_in_schema=False)
async def summon_pool() -> APIResponse:
    try:
        return APIResponse(data=get_summon_pool())
    except SummonConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/summon/collection", response_model=APIResponse, tags=["summon"])
@app.get("/api/v1/summon/collection", response_model=APIResponse, tags=["summon"], include_in_schema=False)
async def summon_collection(x_player_id: str = Header(..., alias="X-Player-ID")) -> APIResponse:
    player = await app.state.database.players.find_one({"id": x_player_id}, {"_id": 1})
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return APIResponse(data=await get_collection(app.state.database, x_player_id))


@app.post("/api/summon", response_model=APIResponse, tags=["summon"])
@app.post("/api/v1/summon", response_model=APIResponse, tags=["summon"], include_in_schema=False)
async def summon(payload: SummonRequest, x_player_id: str = Header(..., alias="X-Player-ID")) -> APIResponse:
    try:
        return APIResponse(data=await perform_summon(app.state.database, x_player_id, payload.request_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientAether as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except SummonConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/quest/current", response_model=APIResponse, tags=["quest"])
@app.get("/api/v1/quest/current", response_model=APIResponse, tags=["quest"], include_in_schema=False)
async def get_current_quest(x_player_id: str = Header(..., alias="X-Player-ID")) -> APIResponse:
    document = await app.state.database.quests.find_one(
        {"player_id": x_player_id, "status": {"$in": [QuestStatus.AVAILABLE.value, QuestStatus.ACTIVE.value]}},
        sort=[("created_at", -1)],
    )
    if document is None:
        return APIResponse(data=None)
    document.pop("_id", None)
    return APIResponse(data=Quest.model_validate(document))


@app.post("/api/quest/{quest_id}/start", response_model=APIResponse, tags=["quest"])
@app.post("/api/v1/quest/{quest_id}/start", response_model=APIResponse, tags=["quest"], include_in_schema=False)
async def start_quest(quest_id: str, x_player_id: str = Header(..., alias="X-Player-ID")) -> APIResponse:
    quest = await app.state.database.quests.find_one({"id": quest_id, "player_id": x_player_id})
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    if quest["status"] not in {QuestStatus.AVAILABLE.value, QuestStatus.ACTIVE.value}:
        raise HTTPException(status_code=409, detail="Quest is no longer available")
    now = datetime.now(timezone.utc)
    await app.state.database.quests.update_one({"id": quest_id, "player_id": x_player_id}, {"$set": {"status": QuestStatus.ACTIVE.value}})
    attempt = await app.state.database.quest_attempts.find_one({"quest_id": quest_id, "player_id": x_player_id})
    if attempt is None:
        attempt = {"id": str(uuid4()), "quest_id": quest_id, "player_id": x_player_id,
                   "status": QuestStatus.ACTIVE.value, "started_at": now.isoformat(), "objective_progress": {}}
        await app.state.database.quest_attempts.insert_one(attempt)
    return APIResponse(data={"quest_id": quest_id, "status": "active", "started_at": attempt["started_at"]})


@app.post("/api/quest/{quest_id}/objectives/{objective_id}/verify", response_model=APIResponse, tags=["quest"])
@app.post("/api/v1/quest/{quest_id}/objectives/{objective_id}/verify", response_model=APIResponse, tags=["quest"], include_in_schema=False)
async def verify_objective(quest_id: str, objective_id: str, payload: dict,
                           x_player_id: str = Header(..., alias="X-Player-ID")) -> APIResponse:
    quest = await app.state.database.quests.find_one({"id": quest_id, "player_id": x_player_id, "status": QuestStatus.ACTIVE.value})
    if quest is None:
        raise HTTPException(status_code=404, detail="Active quest not found")
    objective = next((item for item in quest["objectives"] if item["id"] == objective_id), None)
    if objective is None:
        raise HTTPException(status_code=404, detail="Objective not found")
    if objective.get("verification") == "ai_review":
        result = await VisionVerification().verify(image_base64=payload.get("image_base64", ""), objective=objective["description"])
    elif objective.get("verification") == "self_reported":
        result = await SelfVerification().verify(confirmed=payload.get("confirmed") is True)
    else:
        raise HTTPException(status_code=422, detail="This verification method is not available yet")
    if not result["verified"]:
        return APIResponse(data=result)
    attempt = await app.state.database.quest_attempts.find_one({"quest_id": quest_id, "player_id": x_player_id})
    progress = dict((attempt or {}).get("objective_progress", {}))
    already_verified = progress.get(objective_id, False)
    rewards = []
    if not already_verified:
        attempt_id = (attempt or {}).get("id", quest_id)
        rewards.append(await add_xp(app.state.database, x_player_id, f"objective:{attempt_id}:{objective_id}", ProgressionEventType.OBJECTIVE_COMPLETE, quest_id))
        if objective.get("optional", False):
            rewards.append(await add_xp(app.state.database, x_player_id, f"bonus:{attempt_id}:{objective_id}", ProgressionEventType.BONUS_OBJECTIVE, quest_id))
        await app.state.database.quest_attempts.update_one(
            {"quest_id": quest_id, "player_id": x_player_id},
            {"$set": {f"objective_progress.{objective_id}": True}},
        )
        attempt = await app.state.database.quest_attempts.find_one({"quest_id": quest_id, "player_id": x_player_id})
        progress = dict((attempt or {}).get("objective_progress", {}))
    required = [item["id"] for item in quest["objectives"] if not item.get("optional", False)]
    completed = all(progress.get(item_id) for item_id in required)
    if completed:
        rewards.append(await add_xp(app.state.database, x_player_id, f"quest:{quest_id}", ProgressionEventType.QUEST_COMPLETE, quest_id))
        await earn_aether(app.state.database, x_player_id, f"quest-clear:{quest_id}", QUEST_COMPLETE_AETHER, quest_id)
        await app.state.database.quest_attempts.update_one(
            {"quest_id": quest_id, "player_id": x_player_id, "status": QuestStatus.ACTIVE.value},
            {"$set": {"completed_at": datetime.now(timezone.utc).isoformat(), "status": QuestStatus.COMPLETED.value}},
        )
        completion = await app.state.database.quests.update_one(
            {"id": quest_id, "player_id": x_player_id, "status": QuestStatus.ACTIVE.value},
            {"$set": {"status": QuestStatus.COMPLETED.value}},
        )
        if completion.modified_count:
            await app.state.database.players.update_one(
                {"id": x_player_id},
                {"$addToSet": {"progress.completed_quest_ids": quest_id}},
            )
    player_after = await app.state.database.players.find_one({"id": x_player_id}, {"level": 1, "experience": 1, "stats": 1})
    after = int((player_after or {}).get("level", 1))
    new_rewards = [item for item in rewards if not item.get("already_awarded")]
    before = min((item["level_before"] for item in new_rewards), default=after)
    stat_increases: dict[str, int] = {}
    for reward in new_rewards:
        for stat, count in reward.get("stat_increases", {}).items():
            stat_increases[stat] = stat_increases.get(stat, 0) + count
    xp_awarded = sum(item["xp"] for item in new_rewards)
    return APIResponse(data={**result, "objective_progress": progress, "quest_completed": completed, "already_verified": already_verified,
                             "xp_awarded": xp_awarded, "progression_events": rewards,
                             "level_before": before, "level_after": after,
                             "levels_gained": max(0, after - before), "stat_increases": stat_increases,
                             "experience_after": int((player_after or {}).get("experience", 0))})


@app.get("/api/aether/ledger", response_model=APIResponse, tags=["economy"])
@app.get("/api/v1/aether/ledger", response_model=APIResponse, tags=["economy"], include_in_schema=False)
async def get_aether_ledger(
    limit: int = Query(default=50, ge=1, le=100),
    x_player_id: str = Header(..., alias="X-Player-ID"),
) -> APIResponse:
    if await app.state.database.players.find_one({"id": x_player_id}, {"id": 1}) is None:
        raise HTTPException(status_code=404, detail="Player not found")
    entries = await app.state.database.aether_ledger.find({"player_id": x_player_id}).sort("created_at", -1).limit(limit).to_list(length=limit)
    for entry in entries:
        entry.pop("_id", None)
    return APIResponse(data=[AetherTransaction.model_validate(entry) for entry in entries])


@app.get("/api/progress", response_model=APIResponse, tags=["progression"])
@app.get("/api/v1/progress", response_model=APIResponse, tags=["progression"], include_in_schema=False)
async def get_progress(x_player_id: str = Header(..., alias="X-Player-ID")) -> APIResponse:
    player = await app.state.database.players.find_one({"id": x_player_id})
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    level = int(player.get("level", 1))
    experience = int(player.get("experience", 0))
    threshold = calculate_next_level_xp(level)
    events = await app.state.database.progression_events.find({"player_id": x_player_id}).sort("created_at", -1).limit(20).to_list(length=20)
    for event in events:
        event.pop("_id", None)
    return APIResponse(data={"level": level, "experience": experience, "experience_to_next_level": threshold,
                             "progress_percent": min(100, round(experience * 100 / threshold)),
                             "total_experience": int(player.get("total_experience", experience)),
                             "stats": player.get("stats", {}),
                             "completed_quest_ids": (player.get("progress") or {}).get("completed_quest_ids", []),
                             "recent_events": events})


@app.get("/api/progress/stats", response_model=APIResponse, tags=["progression"])
@app.get("/api/v1/progress/stats", response_model=APIResponse, tags=["progression"], include_in_schema=False)
async def get_progress_stats(x_player_id: str = Header(..., alias="X-Player-ID")) -> APIResponse:
    player = await app.state.database.players.find_one({"id": x_player_id})
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    summary = await app.state.database.progression_events.aggregate([
        {"$match": {"player_id": x_player_id}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}, "xp": {"$sum": "$xp"}}},
    ]).to_list(length=20)
    discoveries = await app.state.database.discoveries.count_documents({"player_id": x_player_id})
    progress = player.get("progress") or {}
    return APIResponse(data={"level": player.get("level", 1), "total_experience": player.get("total_experience", player.get("experience", 0)),
                             "completed_quests": len(progress.get("completed_quest_ids", [])), "discoveries": discoveries,
                             "attributes": player.get("stats", {}),
                             "reward_events": [{"event_type": row["_id"], "count": row["count"], "xp": row["xp"]} for row in summary]})


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"data": None, "error": {"code": "http_error", "message": str(exc.detail)}, "meta": {}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"data": None, "error": {"code": "validation_error", "message": "Request validation failed", "details": {"issues": exc.errors()}}, "meta": {}},
    )


@app.get("/api/v1/health", response_model=APIResponse, tags=["system"])
async def health() -> APIResponse:
    return APIResponse(data={"status": "ok", "service": "api", "version": app.version})


@app.get("/api/v1/health/database", response_model=APIResponse, tags=["system"])
async def database_health() -> APIResponse:
    await app.state.mongo_client.admin.command("ping")
    return APIResponse(data={"status": "ok", "service": "mongodb", "database": settings.mongodb_database})


@app.get("/api/v1/health/ai", response_model=APIResponse, tags=["system"])
async def ai_health() -> APIResponse:
    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
    available = any(model.get("name", "").startswith(settings.ollama_model) for model in models)
    return APIResponse(data={"status": "ok" if available else "model_missing", "service": "ollama", "model": settings.ollama_model})
