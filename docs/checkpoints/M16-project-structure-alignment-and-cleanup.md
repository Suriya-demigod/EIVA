# M16 — Project structure alignment and cleanup

**Status:** [x] Complete

## What this builds

Aligns active EIVA source files with the PROJECT-JARVIS directory layout while preserving the working FastAPI, native-module frontend, and configured-MCP architecture.

## Files changed

- `frontend/app/api.mjs` → `frontend/src/api.mjs` — moved the shared JSON and streaming chat client.
- `frontend/app/app.js` → `frontend/src/app.js` — moved the workspace application entry module.
- `frontend/app/index.html` → `frontend/src/index.html` — moved the FastAPI-served workspace page.
- `frontend/app/state.mjs` → `frontend/src/state.mjs` — moved frontend state handling.
- `frontend/app/styles.css` → `frontend/src/styles.css` — moved workspace styling.
- `frontend/voice/*` → `frontend/src/voice/*` — colocated the standalone voice studio under the frontend source root.
- `backend/skills/available/*.yaml` — moved validated skill manifests out of general application config.
- `backend/main.py` — serves both frontend entry points from `frontend/src/`.
- `backend/config.py` — defaults the skill manifest directory to `backend/skills/available/`.
- `scripts/evaluate_runtime_m00_m07.py` — loads skills from their new package location.
- `scripts/evaluate_voice.py` — reads the relocated voice assets.
- `tests/test_frontend_stream.mjs` — imports the chat streaming module from its new location.
- `docs/CONFIGURATION.md` — documents the new default skill path.
- `README.md` — records the current architecture and directory responsibilities.
- `docs/IMPLEMENTATION_PLAN.md` — adds the M16 scope and completion criteria.
- `milestone.md` — records M16 completion after evaluation.
- `package.json`, `frontend/src/App.jsx`, and empty `frontend/src/components/*` — removed as unused, zero-content React scaffolding; EIVA has no React build or package dependencies.
- `config/skills/` — removed after moving all manifests to the backend skill package.

## Evaluation

- [x] FastAPI serves the workspace and voice pages from `frontend/src/` (workspace, app JS, CSS, voice page, and voice JS returned HTTP 200 after restart).
- [x] The chat stream test resolves its relocated frontend module.
- [x] Skill loading and agent evaluation use `backend/skills/available/`.
- [x] Full local release checks pass: 27 Python tests, module evaluations, compilation, dependency check, and 2 Node tests.
- [x] `git diff --check` passes.

## Architecture notes

- MCP servers remain external executables selected by `config/mcp_servers.yaml`; `backend/mcp/client.py` and the tool gateway are the shared integration layer. The empty server directories are not treated as bundled server implementations.
- Runtime knowledge remains in `data/knowledge`; persistent user data and model caches are not moved as part of source cleanup.
- The front end uses native ES modules to retain its current no-build startup flow. React components are not introduced by this directory alignment.
