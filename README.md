# Re-Alm# RE — Realm Engine

RE is an AI-guided game world. This repository contains a Next.js and TypeScript web app, a versioned FastAPI service, MongoDB persistence, local Ollama/Gemma integration, and shared domain contracts. Phase 1 player setup and the Phase 2 AI Game Master quest loop are implemented.

## Stack

- Web: Next.js App Router, React, TypeScript, Tailwind CSS, PWA manifest foundation
- API: FastAPI, Python 3.12+, Pydantic
- Data: MongoDB, with MongoDB Atlas for shared environments and Compose for local development
- AI: Gemma through Ollama for local development
- Workspace: pnpm monorepo

## Quick start

Prerequisites: Node.js 20+, pnpm 9+, Python 3.12+, and Docker Compose.

```powershell
Copy-Item .env.example .env
docker compose up -d mongo ollama
docker compose exec ollama ollama pull gemma3:4b
pnpm install
pnpm dev:web
```

In a second terminal, start the API:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The web app runs at `http://localhost:3000`. API endpoints are under `/api/v1`; interactive API docs are at `http://localhost:8000/docs`. Player setup is under `/api/v1/player`, and `POST /api/v1/quest/generate` asks Gemma for a validated, personalized quest. Mongo and AI readiness checks are `/api/v1/health/database` and `/api/v1/health/ai`. API startup does not require dependencies to be online; those endpoints report dependency readiness.

For Atlas, put its connection URI in `MONGODB_URI` in `.env` and do not start the local Mongo service. For host-installed Ollama, set `OLLAMA_BASE_URL` as appropriate. Keep `.env` private.

## Repository map

```text
apps/web       Next.js client
apps/api       FastAPI service and Pydantic contracts
packages/types Shared TypeScript contracts
packages/config Shared configuration notes
packages/ui    Shared UI primitives
ai/            Prompts, JSON schemas, evaluator notes
docs/          Architecture, gameplay, AI, and API decisions
```

## Project standards

`main` is the protected integration and release branch. Work on `feat/*`, `fix/*`, `docs/*`, or `chore/*` branches and merge by pull request. Commit messages follow Conventional Commits, such as `feat(api): add quest contract`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Contracts

The initial entities are Player, Quest, Objective, QuestAttempt, Reward, InventoryItem, Summon, Discovery, Progress, NPC, and WorldEvent. Rarity, verification, and quest status enums plus API and error envelopes are documented in [API contracts](docs/api/contracts.md). AI quest proposals follow [the JSON Schema](ai/schemas/quest-output.schema.json) and are treated as untrusted input.

## License

MIT. See [LICENSE](LICENSE).
