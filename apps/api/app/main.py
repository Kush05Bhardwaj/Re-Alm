from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Header
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
)
from .game_master import QuestGenerationError, generate_quest
from .verification import SelfVerification, VisionVerification


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
        aether_reward=proposal.aether_reward,
        status=QuestStatus.AVAILABLE,
        level=player.level,
        created_at=datetime.now(timezone.utc),
    )
    await app.state.database.quests.insert_one(quest.model_dump(mode="json"))
    return APIResponse(data=quest)


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
    progress[objective_id] = True
    required = [item["id"] for item in quest["objectives"] if not item.get("optional", False)]
    completed = all(progress.get(item_id) for item_id in required)
    await app.state.database.quest_attempts.update_one({"quest_id": quest_id, "player_id": x_player_id}, {"$set": {"objective_progress": progress, **({"completed_at": datetime.now(timezone.utc).isoformat(), "status": "completed"} if completed else {})}})
    if completed:
        await app.state.database.quests.update_one({"id": quest_id, "player_id": x_player_id}, {"$set": {"status": QuestStatus.COMPLETED.value}})
        await app.state.database.players.update_one({"id": x_player_id}, {"$inc": {"experience": quest["xp_reward"], "aether": quest["aether_reward"]}})
    return APIResponse(data={**result, "objective_progress": progress, "quest_completed": completed})


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
