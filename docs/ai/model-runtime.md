# AI model runtime

Gemma is the initial Game Master model, served locally through Ollama during development. Configure `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in `.env`. `gemma3:4b` is the Compose development default; change it to a Gemma tag supported by the local Ollama installation if needed. Check `/api/v1/health/ai` for runtime and model availability.

AI output is a proposal, never authoritative game state. Validate it against both Pydantic and the checked-in JSON Schema, then run safety and balance evaluators before persistence or display. No gameplay generation endpoint is part of Phase 0.
