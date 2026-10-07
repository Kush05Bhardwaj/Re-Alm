# API contracts

All endpoints are versioned under `/api/v1`. Successful responses use `{ "data": ..., "error": null, "meta": {} }`. Errors use `{ "data": null, "error": { "code": "...", "message": "...", "details": {}, "request_id": "..." }, "meta": {} }`. Omit optional error fields when unavailable. HTTP status codes remain authoritative; do not encode failures as successful HTTP responses.

Pydantic models in `apps/api/app/contracts.py` are the backend source of truth for the initial domain entities. Their frontend equivalents are in `packages/types/src/index.ts`. AI quest proposals use `AIQuestOutput` and `ai/schemas/quest-output.schema.json`; model output is untrusted and must be validated before use. Server-generated IDs and state must override any model-provided values.

Enums:

- Rarity: `common`, `uncommon`, `rare`, `epic`, `legendary`.
- Verification: `self_reported`, `ai_review`, `server_validated`, `human_review`.
- Quest status: `draft`, `available`, `active`, `completed`, `failed`, `abandoned`.

Initial entities: Player, Quest, Objective, QuestAttempt, Reward, InventoryItem, Summon, Discovery, Progress, NPC, and WorldEvent.
