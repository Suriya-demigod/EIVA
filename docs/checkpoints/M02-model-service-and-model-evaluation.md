# M02 — Model service and model evaluation

**Status:** [x] Complete  
**State:** Complete

## What this builds

Central Groq client lifecycle, configurable model roles, bounded retry/timeout behavior, token and latency tracking, versioned prompts, and a repeatable evaluation dataset/report.

## Files changed in this milestone

- `backend/config.py` — bounded Groq timeout and retry settings
- `backend/core/model_router.py` — Groq-only role routing, latency/token/failure telemetry, and client close support
- `backend/lifecycle.py` — closes the cached Groq client during application shutdown
- `backend/main.py` — wires the planned lifecycle module into FastAPI
- `backend/api/routes/chat.py` — request-correlated model calls and streaming timing telemetry
- `backend/evaluations/__init__.py`
- `backend/evaluations/datasets/model_screening_v1.json` — versioned five-case evaluation set
- `backend/evaluations/model_eval.py` — candidate runner, rubric scoring, latency/token report
- `backend/observability/__init__.py`
- `backend/observability/logging.py` — safe EIVA telemetry logger
- `scripts/evaluate_models.py` — CLI entry point for the evaluation runner
- `.env.example` — timeout/retry configuration examples
- `data/model_evaluation.json` — generated M02 model comparison report
- `docs/checkpoints/M02-model-service-and-model-evaluation.md` — file log and evaluation
- `docs/IMPLEMENTATION_PLAN.md` — M02 completion state
- `milestone.md` — project progress and benchmark result

## Evaluation

Dataset `1.0.1` comparison of both configured candidates on five cases (planning, coding, code review, tool selection, concise response):

- `openai/gpt-oss-120b`: 5/5 cases, 13/13 criteria, mean latency 854 ms, 1,469 total tokens.
- `openai/gpt-oss-20b`: 5/5 cases, 13/13 criteria, mean latency 832 ms, 1,651 total tokens.
- Human spot check of the tool-permission and concise-answer outputs found both models followed the intended behavior.
- A rubric false negative for the valid phrase “Please confirm” was corrected and the dataset version bumped from 1.0.0 to 1.0.1 before recording these final results.
- Both scores are tied on this small screen. Keep role assignments provisional; the observed latency/token differences are too small and the dataset too small to justify changing them.
- A live chat smoke confirmed the response contains model usage, the service logs latency/token counts without logging response text, and streaming logs duration and first-delta timing.
- A graceful Ctrl+C shutdown after a chat request reached “Application shutdown complete,” exercising the FastAPI lifespan client cleanup.
- An invalid model produced a sanitized 502 API response and a failure metric containing only the error type and request metadata.

Report: `data/model_evaluation.json`.

## Completion checks

- [x] All model access goes through the Groq service.
- [x] Role-to-model mapping is configuration driven.
- [x] Evaluation records results without secrets and supports human review.
- [x] Transient errors and timeouts have bounded handling (`45` second timeout, `2` SDK retries).

## Remaining work

None for M02. M03 is waiting for the user's instruction.

