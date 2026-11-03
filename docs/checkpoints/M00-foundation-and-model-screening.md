# M00 — Foundation and model screening

**Status:** [x] Complete  
**State:** Complete

## What this builds

Python project setup, FastAPI entry point, configuration, Groq model routing, health endpoint, and a baseline model screening script.

## Files changed in this milestone

- `AGENTS.md` — workspace note for the Python executable and secret handling
- `.gitignore` — excludes local environment, secrets, caches, and evaluation output
- `.env.example` — Groq key placeholder
- `README.md` — links to the visual dashboard and roadmap; setup commands are in `milestone.md`
- `requirements.txt` — backend dependencies
- `backend/__init__.py`, `backend/config.py`, `backend/main.py`
- `backend/core/__init__.py`, `backend/core/model_router.py`
- `config/models.yaml`
- `scripts/evaluate_models.py`
- `data/model_evaluation.json` — generated baseline comparison report
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/MILESTONE_CHECKLIST.md` — removed; the visual dashboard is now the root `milestone.md`
- `docs/checkpoints/M00-foundation-and-model-screening.md` — checkpoint status, file log, and evaluation notes
- `milestone.md` — visual milestone dashboard and project progress

## Evaluation

- Initial Groq screen: both `openai/gpt-oss-120b` and `openai/gpt-oss-20b` passed 9/9 heuristic checks across three small prompts.
- Mean response time: approximately 1.7 seconds for 120B and 1.0 second for 20B in that run.
- Python compilation and app import succeeded; `/health` is registered.
- The heuristic screen is preliminary and does not determine final model roles.

## Completion checks

- [x] Health endpoint returns a successful response through an HTTP client (`200`, `{"status":"ok","service":"EIVA"}`).
- [x] Candidate model screening can call Groq and save a local report without exposing the API key.
- [x] Project Python source compiles and the app imports.
- [x] Document setup and model-screening commands.

## Remaining work

None for M00. Start M01 only after the user gives the go-ahead.
