# M13 — External agent communication

**Status:** [x] Complete

## What this builds

Internal message types and bus, then optional authenticated A2A client/server and agent cards for configured external agents.

## Files changed in this milestone

- `backend/agents/messaging.py` — typed bounded task-scoped internal message bus
- `backend/agents/base.py` — agent context send/read helpers with recipient validation
- `backend/agents/registry.py` — inject the message bus and configured recipient set
- `backend/agents/a2a.py` — configured peer loader and authenticated A2A 1.0 HTTP+JSON client
- `backend/api/routes/a2a.py` — opt-in Agent Card, inbound A2A messages/task status, and task-scoped outbound dispatch
- `backend/api/routes/__init__.py` — export A2A routes
- `backend/main.py` — register A2A routes
- `backend/config.py` — disabled-by-default A2A settings and token validation
- `backend/lifecycle.py` — initialize and close the internal bus and A2A client
- `config/a2a_peers.yaml` — empty explicit peer allowlist and credential-variable format
- `requirements.txt` — declare the async HTTP client dependency
- `tests/test_agent_communication.py` — message isolation, authentication, card, client, failure, and trace tests
- `README.md` — opt-in setup, API routes, and supported protocol scope
- `docs/IMPLEMENTATION_PLAN.md` — M13 completion state and limitations
- `docs/checkpoints/M13-external-agent-communication.md` — completion and evaluation record
- `milestone.md` — mark M13 complete and queue M14

## Evaluation

Evaluations passed:

- `python -m compileall -q backend scripts tests`
- `python -m unittest discover -s tests` — 12 tests passed
- `python -m scripts.verify_tool_policies` — all 16 tool bindings passed
- `python -m scripts.evaluate_runtime_m00_m07` — local orchestration, workflow handoffs, cancellation, concurrency, and task SSE passed with A2A disabled
- Mock HTTP transport verified Agent Card discovery, origin constraints, bearer header, A2A version and message shape, peer failure containment, and response validation
- FastAPI checks verified disabled routes, invalid bearer rejection, text message validation, local research-task handoff, and task-scoped event/message records

No live external A2A peer was contacted. The shared token and peer endpoint configuration were exercised with fake local transports.

## Completion checks

- [x] External messages are authenticated and validated.
- [x] Communication can be disabled without affecting local EIVA.
- [x] Failures and handoffs are traceable.

## Initial scope limits

A2A streaming, push notifications, binary attachments, and follow-up messages are not implemented. The server accepts new text requests, and remote peers can query task status. Only explicitly configured peers can be contacted; peer cards must use HTTPS and the service endpoint must share the card's origin. HTTP is accepted only for loopback development.

