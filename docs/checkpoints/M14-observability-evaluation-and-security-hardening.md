# M14 — Observability, evaluation, and security hardening

**Status:** [x] Complete

## What this builds

Structured logs, tracing, metrics, cost/token tracking, model/agent/tool evaluations, safety checks, failure injection, dependency review, and secret-handling review.

## Files changed in this milestone

- `backend/observability/logging.py` — JSON console logs, request correlation, and redaction for bearer/API credentials
- `backend/main.py` — request-scoped logging correlation context
- `backend/api/errors.py` — safe unexpected-error diagnostics and request ID response header
- `backend/core/model_router.py` — optional per-model token cost estimates alongside existing latency and usage telemetry
- `backend/evaluations/model_eval.py` — optional cost reporting and credential redaction before writing evaluation artifacts
- `config/models.yaml` — optional provider-contract pricing table, empty by default
- `tests/test_observability_security.py` — structured log, credential redaction, cost, and unexpected-error regression checks
- `docs/checkpoints/M14-observability-evaluation-and-security-hardening.md` — M14 implementation and evaluation record
- `docs/IMPLEMENTATION_PLAN.md` — M14 completed state and known release risks
- `milestone.md` — dashboard advanced to M15

## Evaluation

The broad evaluation pass used local and mocked provider/tool calls. It did not make paid Groq calls or contact external A2A peers.

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | ✅ 17 tests passed, including M13 A2A, RAG, vision, voice, frontend application, and M14 safety checks |
| `python -m scripts.verify_tool_policies` | ✅ Tool schemas, permissions, audit, and browser mappings passed |
| `python -m scripts.verify_orchestration` | ✅ Task transitions, event replay, and handoff graph passed |
| `python -m scripts.evaluate_runtime_m00_m07` | ✅ Agent, skill, MCP, workflow, failure recovery, cancellation, concurrency, and task SSE checks passed |
| `python -m scripts.evaluate_persistence` | ✅ Migration, restart recovery, event/checkpoint persistence, and scoped memory checks passed |
| `python -m scripts.evaluate_rag` | ✅ Loaders, chunking, embeddings, SQLite vector/FTS, hybrid retrieval, confinement, and citations passed |
| `node --test tests/test_frontend_stream.mjs` | ✅ 2 tests passed |
| `python -m compileall -q backend scripts tests` | ✅ Passed |
| `python -m pip check` | ✅ No broken installed requirements |
| `git diff --check` | ✅ Passed |

During failure injection, an unexpected server error was found to lose its request ID in the structured log and response header because Starlette handles it outside the request middleware. The error handler now restores correlation for the diagnostic and returns `X-Request-ID`; a real in-process HTTP regression covers the case.

## Completion checks

- [x] Runs can be traced end to end.
- [x] Model quality, latency, and cost are measurable.
- [x] Critical routes and workflows have automated coverage.
- [x] Secrets are absent from logs and reports.
- [x] Known risks and limitations are documented.

## Evaluation notes and limits

- Model screening remains a small regex-scored set requiring human review; no live Groq comparison was repeated during this local hardening pass.
- Cost estimates are deliberately unavailable until per-model input/output rates are configured from the applicable provider contract. Audio costs are not estimated.
- Streaming calls report latency, first-token time, output chunk count, and estimated input tokens; provider usage metadata may not be available on the stream-start event, so streaming completion cost is not currently reported.
- `pip check` passed, and dependency ranges in `requirements.txt` were reviewed. `pip-audit` is not installed, so no vulnerability-database scan was run and no extra audit dependency was added. Run a dependency advisory scan during release preparation.
- Existing Starlette emits a `TestClient`/httpx deprecation warning. It does not fail tests; address it with the dependency compatibility review in M15.
- External MCP servers and external A2A peers remain unconfigured and were not contacted. Their live integration checks remain environment-dependent.

