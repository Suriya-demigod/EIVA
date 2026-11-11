# M15 — Packaging, setup, and release readiness

**Status:** [x] Complete

## What this builds

Setup scripts, local run commands, optional container configuration, configuration reference, migration/backup guidance, and user-facing documentation.

## Files changed in this milestone

- `README.md` — Windows quick start, first-run instructions, corrected optional feature variable names, and operations links
- `docs/CONFIGURATION.md` — environment variable and YAML configuration reference
- `docs/OPERATIONS.md` — start, upgrade, migration, SQLite backup/restore, release checks, and deployment limits
- `docs/checkpoints/M10-voice-interface.md` — historical variable-name correction linking to the current configuration reference
- `frontend/voice/voice.js` — voice-disabled guidance corrected to the actual `VOICE_ENABLED` setting
- `scripts/evaluate_voice.py` — regression assertion for the voice setting name
- `scripts/setup.ps1` — Python/virtual-environment setup and dependency installation
- `scripts/release_check.ps1` — repeatable local release gate
- `scripts/backup_database.py` — consistent SQLite online backup with integrity validation
- `tests/test_database_backup.py` — WAL data, integrity, missing source, and no-overwrite checks
- `.gitignore` — excludes local database backups
- `docs/IMPLEMENTATION_PLAN.md` — M15 completed state and deployment boundaries
- `docs/checkpoints/M15-packaging-setup-and-release-readiness.md` — M15 implementation and evaluation record
- `milestone.md` — dashboard advanced to project completion

## Evaluation

| Check | Result |
|---|---|
| `scripts/setup.ps1` | ✅ Created/validated the workspace venv and installed dependencies; all declared requirements were already satisfied in this environment |
| `scripts/release_check.ps1` | ✅ 19 Python tests, tool/orchestration/runtime/persistence/RAG/voice evaluations, compilation, dependency consistency, and 2 Node frontend tests passed |
| `tests/test_database_backup.py` | ✅ 2 tests passed, including a WAL-backed consistent snapshot, integrity validation, and refusal to overwrite an existing backup |
| Local startup on `127.0.0.1:18765` | ✅ FastAPI startup completed; `/health` returned `ok`; frontend `/` returned HTTP 200 |
| `git diff --check` | ✅ Passed |

The setup command and complete release script were run. Dependencies were already present in the existing project virtual environment, so a separate empty-environment package download was not performed. The release-check suite uses local mocks and does not call external integrations; the single minimal live Groq diagnostic is recorded below.

## Follow-up diagnostics from the user screenshots

- The voice page's disabled-state hint had retained the incorrect `EIVA_VOICE_ENABLED` name. It now directs users to `VOICE_ENABLED=true`, and the voice evaluation checks that the displayed setting matches the backend.
- One minimal request through the existing Groq model router failed as `APIConnectionError` (no HTTP status). DNS resolved `api.groq.com`, but the local HTTPS connectivity probe to port 443 failed. This points to blocked/unavailable outbound network connectivity; the API key was not printed or inspected. Restore outbound HTTPS access to `api.groq.com` and retry chat. Voice remains disabled until `VOICE_ENABLED=true` is added to `.env` and the application is restarted.

## Completion checks

- [x] A clean environment can install and configure EIVA from the docs.
- [x] Start, update, migration, and backup steps are documented and usable.
- [x] Release checks pass and known limitations are listed.

## Evaluation notes and limits

- The supported setup documented here is local Windows/PowerShell development. Node.js is optional; the web app uses native browser modules and has no build step. No container configuration was added because it is not needed for this local release scope.
- `.env` remains local and Git-ignored. The documented environment variable names match the actual settings fields (`VOICE_ENABLED`, `A2A_ENABLED`, etc.); the prior README references incorrectly used an `EIVA_` prefix and have been corrected.
- SQLite backups use the SQLite online backup API to include committed WAL data. Stop the service before restoring a backup.
- The install check reused the existing `.venv`; dependency versions are bounded in `requirements.txt` but are not captured in a lock file.
- `pip check` passes. `pip-audit` is unavailable, so a vulnerability-database scan remains a release follow-up. The existing Starlette `TestClient`/httpx deprecation warning also remains for dependency compatibility review.
- This is a single-user local application, not a production or multi-user internet-facing deployment. Production authentication, hardened hosting, and external MCP/A2A deployment configuration remain outside M15.

