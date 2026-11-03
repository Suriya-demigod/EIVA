# M01 — API contracts and chat foundation

**Status:** [x] Complete  
**State:** Complete

## What this builds

Typed API schemas, chat/agent/task routes, validation, consistent errors, request IDs, and a streaming response contract.

## Files changed in this milestone

- `backend/api/__init__.py`
- `backend/api/schemas.py` — request, response, error, agent, and task contracts
- `backend/api/errors.py` — structured validation, provider, HTTP, and internal error mapping
- `backend/config.py` — versioned API prefix default (`/api/v1`)
- `backend/api/routes/__init__.py`
- `backend/api/routes/chat.py` — non-streaming chat and SSE streaming
- `backend/api/routes/agents.py` — planned-agent discovery contract
- `backend/api/routes/tasks.py` — task list contract
- `backend/main.py` — route registration, request IDs, and exception handlers
- `config/models.yaml` — configured `chat` role
- `docs/IMPLEMENTATION_PLAN.md` — M01 completion state and current boundaries
- `docs/checkpoints/M01-api-contracts-and-chat-foundation.md` — milestone file log and evaluation
- `milestone.md` — progress dashboard

## Evaluation

Verified with a local Uvicorn process and live requests:

- `GET /health`: HTTP 200.
- Versioned `POST /api/v1/chat`: HTTP 200 with Groq response, model ID, and request ID in body/header.
- Versioned streaming chat: HTTP 200 with `token` and `done` SSE events.
- `GET /api/v1/agents`: four agents listed with `planned` status.
- `GET /api/v1/tasks`: empty task list, as task execution is not implemented yet.
- Empty chat message: HTTP 422, `invalid_request`, request ID included.
- Temporarily invalid model ID: HTTP 502, sanitized `provider_unavailable` response with request ID; original model configuration was restored.
- Python compilation completed successfully.

## Completion checks

- [x] A client can submit a chat message and receive a response.
- [x] Streaming and non-streaming contracts are documented and usable.
- [x] Invalid input and provider failures return structured errors.

## Remaining work

None for M01. M02 is waiting for the user's instruction.

