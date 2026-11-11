# M12 — Frontend application

**Status:** [x] Complete

## What this builds

Chat, assistant status, voice waveform, agent monitor, vision panel, memory panel, task monitor, settings, API services, state management, and responsive styling.

## Files changed in this milestone

- `backend/api/routes/__init__.py` — register the approval API module
- `backend/api/routes/approvals.py` — list pending approval requests and record decisions
- `backend/api/routes/tasks.py` — include task error and creation metadata for the monitor
- `backend/api/schemas.py` — typed approval response models and task summary metadata
- `backend/core/permission_manager.py` — defer approval verification until the user decision
- `backend/lifecycle.py` — create the approval manager, connect task events, and cancel pending requests at shutdown
- `backend/main.py` — serve the app at `/` and preserve voice at `/voice-ui/`
- `backend/tools/approvals.py` — bounded, task-scoped pending decision queue
- `backend/tools/gateway.py` — wait for decisions, publish events, and describe actions without exposing contents
- `frontend/app/index.html` — main workspace entry page
- `frontend/app/styles.css` — responsive dashboard and feature panel styles
- `frontend/app/app.js` — navigation, chat, tasks, approvals, knowledge, memory, vision, and settings UI
- `frontend/app/api.mjs` — JSON API client and tested chat SSE reader
- `frontend/app/state.mjs` — UI state and conversation persistence
- `frontend/voice/index.html` — preserved standalone voice page
- `frontend/voice/voice.css` — preserved standalone voice styles
- `frontend/voice/voice.js` — preserved standalone voice controls
- `scripts/evaluate_voice.py` — update the voice page evaluation paths
- `tests/test_frontend_application.py` — static route, approval API, and gateway pause/resume checks
- `tests/test_frontend_stream.mjs` — split-frame chat streaming and server error checks
- `README.md` — workspace URL and approval flow documentation
- `docs/IMPLEMENTATION_PLAN.md` — M12 completion state
- `docs/checkpoints/M12-frontend-application.md` — completion and evaluation record
- `milestone.md` — mark M12 complete and queue M13

## Evaluation

Evaluations passed:

- `python -m compileall -q backend scripts tests`
- `python -m unittest discover -s tests` — 6 tests passed, including UI serving, approval API and gateway, RAG, vision, and voice checks
- `node --test tests/test_frontend_stream.mjs` — 2 tests passed for split SSE frames and error events
- Node syntax checks for `app.js`, `api.mjs`, and `state.mjs`
- `python -m scripts.verify_tool_policies` — 16 tool bindings passed
- `python -m scripts.evaluate_runtime_m00_m07` — agent, MCP, workflow, cancellation, concurrency, and task SSE checks passed
- `python -m scripts.evaluate_rag` and `python -m scripts.evaluate_persistence` — passed
- Browser check at desktop and mobile widths; overview, chat, tasks, knowledge, memory, vision, and settings rendered, with no browser console warnings/errors

These checks use fake model/MCP responses; no live Groq request or real Playwright MCP server was used. Starlette emits a deprecation warning for the installed `TestClient`/httpx combination; tests pass, and no dependency was added just to silence it.

## Completion checks

- [x] Core flows work without developer tools.
- [x] Progress, errors, and approval requests are understandable.
- [x] Layout is usable at supported window sizes.

