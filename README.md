# RE:ALM — Realm Engine

RE:ALM is a real-world RPG prototype that turns safe, everyday observations into quests, progression, and collectible adventure content. The player profile and game state live in MongoDB; the web client talks to a FastAPI service that owns quest validation, rewards, summons, and inventory.

## What works today

- Create a player profile with an archetype, interests, and preferred quest duration.
- Generate optional quests from player context with the local Game Master. Unsafe or invalid model output is rejected; a small set of reviewed fallback quests keeps the loop usable if the local model is unavailable.
- Start quests and complete objectives through self-confirmation or image review. Browser geolocation helpers make one-time checks; continuous routes and coordinates are not stored.
- Award XP, level-ups, stat increases, and 30 Aether for a completed quest.
- Spend Aether on server-controlled summons. New content and duplicate refunds are recorded in the ledger and affect the player's collection or future gameplay.
- Browse inventory, item details, rarity progress, and collection discoveries in a responsive web interface.

## Stack

- **Web:** Next.js 15, React 19, TypeScript, Tailwind CSS
- **API:** FastAPI, Pydantic, Python
- **Database:** MongoDB, accessed asynchronously through Motor
- **Local AI:** Ollama; the Game Master model is configurable
- **Workspace:** pnpm monorepo

## Run locally

### Requirements

- Node.js 20 or newer and pnpm 9
- Python 3.12 or newer
- Docker with Compose, or a local MongoDB installation
- Ollama is optional for startup. It enables model-generated quests and photo review; safe fallback quests are available when the Game Master model cannot respond.

### 1. Configure services

From the repository root, create your local environment file and start MongoDB and Ollama:

```powershell
Copy-Item .env.example .env
docker compose up -d mongo ollama
```

Pull the model named by `OLLAMA_MODEL` in `.env` (the example uses `gemma3:4b`):

```powershell
docker compose exec ollama ollama pull gemma3:4b
```

If Ollama is installed directly on your computer, use `ollama pull gemma3:4b` instead. Set `OLLAMA_BASE_URL` to the address reachable by the API. For photo review, set `VISION_MODEL` to an Ollama model that supports image input. The Game Master and vision models can be configured separately.

### 2. Install web dependencies

```powershell
pnpm install
```

### 3. Start the API

In a second terminal, from the repository root:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For macOS or Linux, activate the virtual environment with `source .venv/bin/activate`.

### 4. Start the web app

In another terminal, from the repository root:

```powershell
pnpm dev:web
```

Open [http://localhost:3000](http://localhost:3000). Use `localhost` consistently for the web app; the example API CORS setting allows `http://localhost:3000`. If you use a different web origin, add it to `API_CORS_ORIGINS` in `.env` and restart the API.

The API docs are at [http://localhost:8000/docs](http://localhost:8000/docs). Useful readiness endpoints:

- `GET /api/v1/health` — API process
- `GET /api/v1/health/database` — MongoDB connection
- `GET /api/v1/health/ai` — configured Ollama model

The API can start while MongoDB or Ollama is unavailable; the readiness endpoints report whether each dependency is usable.

### Run the API in Compose instead

Compose can build and start the API, MongoDB, and Ollama together:

```powershell
docker compose up --build
```

The web client is not part of Compose, so install dependencies and run `pnpm dev:web` on the host as above. The first Ollama model download may take a while.

## API overview

Player-specific endpoints expect the `X-Player-ID` header returned when the profile is created. The server owns authoritative progression, Aether balances, summon costs, and random content selection.

| Area | Routes |
| --- | --- |
| Player | `POST /api/v1/player/create`, `GET /api/v1/player/me`, `PATCH /api/v1/player/profile` |
| Quests | `POST /api/v1/quest/generate`, `GET /api/v1/quest/current`, `POST /api/v1/quest/{quest_id}/start` |
| Objective verification | `POST /api/v1/quest/{quest_id}/objectives/{objective_id}/verify` |
| Progression | `GET /api/v1/progress`, `GET /api/v1/progress/stats` |
| Aether | `GET /api/v1/aether/ledger` |
| Summons | `GET /api/v1/summon/pool`, `POST /api/v1/summon`, `GET /api/v1/summon/collection` |
| Inventory | `GET /api/v1/inventory`, `GET /api/v1/inventory/{id}`, `GET /api/v1/collection/progress` |

## Configuration

Copy `.env.example` to `.env` and keep that file private. Common settings:

| Variable | Purpose | Example default |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | API base URL used by the web client | `http://localhost:8000/api/v1` |
| `API_CORS_ORIGINS` | Comma-separated allowed browser origins | `http://localhost:3000` |
| `MONGODB_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGODB_DATABASE` | Database name | `realm` |
| `OLLAMA_BASE_URL` | Ollama address reachable by the API | `http://localhost:11434` |
| `OLLAMA_MODEL` | Game Master model tag | `gemma3:4b` |
| `VISION_MODEL` | Optional image-capable model for photo checks | `gemma3:4b` |
| `SUMMON_COST` | Server-side Aether cost per summon | `30` |
| `SUMMON_RATES` | Server-side rarity weights; must total 100 | R 70, SR 25, SSR 4.5, UR 0.5 |
| `SUMMON_DUPLICATE_REFUNDS` | Aether refund by duplicate rarity | R 5, SR 15, SSR 60, UR 200 |

For MongoDB Atlas, set `MONGODB_URI` to the Atlas connection string and do not start the local MongoDB service. Within Compose, service hostnames are configured automatically for the API container.

## Verification and safety

Quests are optional and must be safe to complete in an ordinary setting. Model output is untrusted and checked on the server for schema, duration, difficulty, rewards, duplication, and unsafe instructions. The client never decides whether XP or Aether was earned.

Self-confirmation supports subjective objectives. Photo review can assess visible evidence, but cannot prove location, time, identity, or events outside the image. Geolocation checks are requested only for a specific check; continuous route tracking is not used. Combined GPS, image, time, and quest-state verification remains future work. See [API contracts](docs/api/contracts.md) for implementation details and limits.

## Repository map

```text
apps/web       Next.js client and responsive game UI
apps/api       FastAPI service, game rules, and persistence
packages/types Shared TypeScript contracts
packages/config Shared configuration notes
packages/ui   Shared UI primitives
ai/            Game Master prompt, output schema, evaluation notes
docs/          Architecture, gameplay, model runtime, and API contracts
```

## Development

Run the available web checks from the repository root:

```powershell
pnpm typecheck
pnpm build:web
```

Work on `feat/*`, `fix/*`, `docs/*`, or `chore/*` branches and merge through a pull request. Commit messages use Conventional Commits, for example `docs: improve local setup guide`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## More documentation

- [Architecture overview](docs/architecture/overview.md)
- [Gameplay contracts](docs/gameplay/contracts.md)
- [API contracts](docs/api/contracts.md)
- [Ollama model runtime](docs/ai/model-runtime.md)
- [Quest output JSON Schema](ai/schemas/quest-output.schema.json)

## License

MIT. See [LICENSE](LICENSE).
