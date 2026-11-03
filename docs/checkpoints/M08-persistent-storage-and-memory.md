# M08 — Persistent storage and memory

**Status:** [x] Complete

## What this builds

Database connection/migrations, repositories, conversation/task/checkpoint records, persistent short-term history, explicitly saved long-term memory, retrieval, and user memory controls.

## Files changed in this milestone

- `.env.example`
- `.gitignore`
- `README.md`
- `backend/api/routes/__init__.py`
- `backend/api/routes/chat.py`
- `backend/api/routes/memories.py`
- `backend/api/routes/tasks.py`
- `backend/api/schemas.py`
- `backend/config.py`
- `backend/database/__init__.py`
- `backend/database/migrations/001_initial.sql`
- `backend/database/models.py`
- `backend/database/repositories.py`
- `backend/lifecycle.py`
- `backend/main.py`
- `backend/memory/manager.py`
- `backend/memory/retrieval.py`
- `backend/memory/short_term.py`
- `backend/orchestration/events.py`
- `backend/orchestration/graph.py`
- `backend/tasks/manager.py`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/checkpoints/M08-persistent-storage-and-memory.md`
- `milestone.md`
- `scripts/evaluate_persistence.py`
- `scripts/migrate_db.py`

## Evaluation

`python -m compileall -q backend scripts` and `python -m scripts.evaluate_persistence` passed; the evaluator uses temporary SQLite databases and verifies migration repeatability, conversation persistence and user/task scope isolation, message truncation, completed-task persistence, interrupted-task recovery, event/checkpoint persistence, memory retrieval isolation, owner-scoped inspection/deletion, memory API status codes, and application lifespan startup. The M00–M07 runtime suite was rerun after persistence integration and still passes. The separate migration command initialized the ignored local database at `data/eiva.sqlite3`; evaluation did not use or alter project database contents or real user data.

## Completion checks

- [x] Versioned SQLite migration and repositories initialize cleanly and are repeatable.
- [x] Conversations, tasks, events, and workflow checkpoints persist with user/task boundaries.
- [x] Explicitly saved memories are retrievable only for the configured local user and can be inspected/deleted through the API.

**Design boundary:** Long-term memory capture is explicit via `POST /api/v1/memories`; EIVA does not silently save every conversation. Retrieval is scoped lexical ranking; semantic/vector retrieval belongs to M09. The current identity is the configured single local user. Tasks and memory survive restarts; active tasks found after restart are marked failed with a recovery explanation rather than resumed.

