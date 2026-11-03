# M04 — Agent base and registry

**Status:** [x] Complete

## What this builds

Shared agent interface, configuration, registry, typed inputs/outputs, lifecycle/cancellation, and structured progress events.

## Files changed in this milestone

- `backend/agents/__init__.py`
- `backend/agents/base.py`
- `backend/agents/registry.py`
- `backend/api/routes/agents.py`
- `backend/api/schemas.py`
- `backend/config.py`
- `config/agents.yaml`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/checkpoints/M04-agent-base-and-registry.md`
- `milestone.md`

## Evaluation

`python -m compileall -q backend scripts` passed. The config-backed registry loads all four definitions; M05 registers concrete implementations. The M00–M07 runtime evaluation exercised the common registry contract with fake agents: progress events, sanitized failure containment, cancellation, and timeout all passed. No live Groq request was made in this check.

## Completion checks

- [x] Agent definitions load by name and concrete implementations share one async interface.
- [x] Typed input/output models validate payloads and results.
- [x] Lifecycle events include progress and safe failure summaries; cancellation and timeout paths are implemented.

**Evaluation note:** Registry execution behavior passed isolated async checks with fake agents. Live model-backed execution is covered by later integration setup, not this deterministic test.

