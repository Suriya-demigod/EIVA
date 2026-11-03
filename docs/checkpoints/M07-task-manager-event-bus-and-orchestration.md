# M07 — Task manager, event bus, and orchestration

**Status:** [x] Complete

## What this builds

Task lifecycle/status, event bus, supervisor/planner, graph execution, handoffs, cancellation, research and coding workflows, and bounded concurrency.

## Files changed in this milestone

- `backend/api/routes/tasks.py`
- `backend/api/schemas.py`
- `backend/lifecycle.py`
- `backend/orchestration/events.py`
- `backend/orchestration/graph.py`
- `backend/orchestration/supervisor.py`
- `backend/orchestration/workflows/coding.py`
- `backend/orchestration/workflows/research.py`
- `backend/tasks/__init__.py`
- `backend/tasks/manager.py`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/evaluations/M00-M07-runtime-review.md`
- `docs/checkpoints/M07-task-manager-event-bus-and-orchestration.md`
- `milestone.md`
- `scripts/verify_orchestration.py`

## Evaluation

`python -m compileall -q backend scripts`, `python -m scripts.verify_orchestration`, `python -m scripts.verify_tool_policies`, and `python -m scripts.evaluate_runtime_m00_m07` passed. The runtime evaluation used fake agents and a local fake MCP stdio server; both research and coding handoffs, safe tool failure recovery, workflow and API cancellation, one-task concurrency bound, task API submit/list/get, and terminal SSE replay passed. No live Groq calls or external MCP servers were used. See the [cross-milestone evaluation](../evaluations/M00-M07-runtime-review.md).

## Completion checks

- [x] Tasks transition through explicit valid states.
- [x] Research and coding graphs hand work between specialist agents and publish progress/events.
- [x] Cancellation and failures end with safe, user-readable explanations.
- [x] Concurrency, task retention, event history, tool calls, agent duration, and provider retries have configured bounds.

**Runtime limitation:** Task records and event history are process-local until M08. Live Groq execution and real MCP server calls remain unverified because no MCP commands are configured; deterministic local async workflows and SSE were verified.

