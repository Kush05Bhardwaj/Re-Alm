# API contracts

All endpoints are versioned under `/api/v1`. Successful responses use `{ "data": ..., "error": null, "meta": {} }`. Errors use `{ "data": null, "error": { "code": "...", "message": "...", "details": {}, "request_id": "..." }, "meta": {} }`. Omit optional error fields when unavailable. HTTP status codes remain authoritative; do not encode failures as successful HTTP responses.

Pydantic models in `apps/api/app/contracts.py` are the backend source of truth for the initial domain entities. Their frontend equivalents are in `packages/types/src/index.ts`. AI quest proposals use `AIQuestOutput` and `ai/schemas/quest-output.schema.json`; model output is untrusted and must be validated before use. Server-generated IDs and state must override any model-provided values.

Enums:

- Rarity: `common`, `uncommon`, `rare`, `epic`, `legendary`.
- Verification: `self_reported`, `ai_review`, `server_validated`, `human_review`.
- Quest status: `draft`, `available`, `active`, `completed`, `failed`, `abandoned`.
- Quest categories: `exploration`, `observation`, `discovery`, `mystery`, `photography`, `challenge`, `chaos`, `story`.

Initial entities: Player, Quest, Objective, QuestAttempt, Reward, InventoryItem, Summon, Discovery, Progress, NPC, and WorldEvent.

The Game Master endpoint `POST /api/v1/quest/generate` uses `X-Player-ID` and an optional bounded environment selection. The API assembles player progression, recent quest history, and discoveries; asks Ollama for schema-constrained JSON; validates structure, safety, duration, difficulty, rewards, and novelty; then assigns server-owned IDs/status and stores the quest. `GET /api/v1/quest/current` returns the player's latest available quest. The client never submits model output or authoritative player progression.

## Real-world verification

The web and API verification services provide self-confirmation, one-shot browser geolocation checks, image review, and a combined location/image pipeline. `calculateDistance` uses the Haversine great-circle formula and returns meters. Browser location requests are made only when a location verifier is explicitly called; coordinates are evaluated in memory and are not stored. The current generated quest path still assigns self-reported verification. The API supports `POST /api/v1/quest/{quest_id}/start` and `POST /api/v1/quest/{quest_id}/objectives/{objective_id}/verify`; required objectives must all pass before quest status and rewards are updated. Photo review uses the configured Ollama `VISION_MODEL` (or `OLLAMA_MODEL` fallback), accepts images up to 8 MB, and requires confidence of at least 0.7. The model is instructed to assess only visible evidence; it cannot establish location, time, identity, or off-camera events. Combined verification currently composes location and image checks; timestamp and quest-state binding remain future work.

Verification never stores a route. Do not author quests requiring trespass, unsafe roads, unsafe animals, strangers, dangerous climbing, or physical danger. Generated quests remain safety-gated by `ai/game_master.py`.

## Progression

XP is awarded through idempotent progression events: `OBJECTIVE_COMPLETE` (+20 XP), `QUEST_COMPLETE` (+100 XP), `BONUS_OBJECTIVE` (+25 XP, in addition to objective XP), and `RARE_DISCOVERY` (+50 XP). Objective and clear rewards use stable event IDs to make request retries safe. Current-level XP carries across levels; each level requires `100 × current_level` XP. Every level gained increases one randomly selected attribute by 1. Event records store the reward source, XP, before/after level, and stat increases.

`GET /api/v1/progress` returns current-level XP, the next threshold, total XP earned, attributes, completed quests, and the 20 most recent reward events. `GET /api/v1/progress/stats` returns aggregate reward-event, discovery, quest, and attribute stats. Both require `X-Player-ID`. Legacy generated quest `xp_reward` remains in the quest contract for compatibility; progression rewards use the event schedule above. Quest Aether rewards are still applied on quest clear.

## Aether economy

Quest clear earns a fixed 30 Aether. The generated quest's legacy `aether_reward` is not authoritative. Each balance operation first creates an `AETHER_EARN`, `AETHER_SPEND`, or `AETHER_REFUND` ledger entry and applies an idempotent player-balance update. The spend helper checks the current server-side balance and rejects a debit that would make it negative; summon costs must come from trusted server logic, never the request body. `GET /api/v1/aether/ledger?limit=50` returns the latest 1–100 ledger entries for the player. The existing player profile returns the current Aether balance. A summon catalog/cost and public summon endpoint are not defined yet, so the protected spend helper is ready for that server-side flow.
