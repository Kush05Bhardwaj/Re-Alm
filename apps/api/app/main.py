from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings
from .contracts import APIResponse


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
