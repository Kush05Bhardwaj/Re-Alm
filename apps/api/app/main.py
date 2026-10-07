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
from .contracts import APIResponse, Player, PlayerCreate, PlayerProfilePatch


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
