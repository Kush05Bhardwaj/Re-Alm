# Architecture overview

RE is a pnpm workspace monorepo. `apps/web` is the Next.js App Router client, `apps/api` is the versioned FastAPI service, and `packages/types` and `packages/ui` hold frontend shared contracts and components. Python Pydantic contracts live with the API. `ai/` holds prompts, JSON schemas, and evaluation notes.

The API owns persistence and authoritative state. MongoDB is accessed asynchronously through Motor; local development uses the MongoDB service in Compose and shared environments use MongoDB Atlas. The API calls Ollama over HTTP for local model access; Gemma is the initial model family. The client communicates with the API only through `/api/v1`.

## Service boundary

```text
Browser → Next.js (3000) → FastAPI (8000) → MongoDB
                                      └──→ Ollama (11434) → Gemma
```

## Local startup

1. Install Node.js 20+, pnpm 9+, Python 3.12+, and Docker Compose.
2. Copy `.env.example` to `.env`.
3. Run `docker compose up -d mongo ollama` from the repository root. For Atlas, set `MONGODB_URI` to the Atlas connection string and omit the local Mongo service.
4. Pull the configured Gemma model with `docker compose exec ollama ollama pull gemma3:4b` (or `ollama pull gemma3:4b` when Ollama runs on the host).
5. In one terminal, run `cd apps/api`, create/activate a virtual environment, install `pip install -r requirements.txt`, then run `uvicorn app.main:app --reload --port 8000`.
6. In another terminal, run `pnpm install` at the root and `pnpm dev:web`.
7. Visit `http://localhost:3000`. API health is at `http://localhost:8000/api/v1/health`; Mongo and Ollama checks are at `/api/v1/health/database` and `/api/v1/health/ai`.

The API process starts even if Mongo or Ollama is unavailable. Their dedicated readiness endpoints indicate whether those dependencies are connected and whether the configured Ollama model is present. Compose can start the API with `docker compose up --build`; it uses local Mongo and Ollama endpoints. `.env` is loaded by Compose and should never be committed.
