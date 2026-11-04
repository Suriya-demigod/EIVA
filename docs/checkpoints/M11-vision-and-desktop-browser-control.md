# M11 — Vision and desktop/browser control

**Status:** [x] Complete

## What this builds

Image analysis and task-scoped Playwright browser control: page screenshots, tab discovery/selection, navigation, semantic clicks, text entry, and key presses.

## Files changed in this milestone

- `backend/config.py` — image upload limit
- `backend/core/model_router.py` — image input through the shared Groq client
- `backend/api/schemas.py` — vision request/response contracts
- `backend/api/routes/vision.py` — supplied-image and task-scoped screenshot analysis
- `backend/api/routes/__init__.py` — route export
- `backend/main.py` — vision route registration
- `backend/tools/schemas.py` — typed Playwright screenshot, tab, click, text, and key actions
- `backend/tools/gateway.py` — task scope enforcement, per-task browser MCP processes, cancellation cleanup
- `backend/mcp/client.py` — bounded MCP response line size for screenshots
- `backend/orchestration/graph.py` — omit screenshot bytes from persisted task results
- `backend/orchestration/supervisor.py` — close task-owned browser process on finish/cancel
- `config/models.yaml` — configurable Groq vision model role
- `config/tool_bindings.yaml` — Playwright screen/tab/input bindings
- `config/permissions.yaml` — read-only and approval-required browser permissions
- `scripts/verify_tool_policies.py` — checks the expanded browser tool set
- `scripts/evaluate_vision.py` — deterministic image, permission, trace, and cancellation evaluation
- `tests/test_vision_pipeline.py` — unittest entry point for the M11 evaluation
- `README.md` — vision endpoints, browser controls, and setup limits
- `docs/IMPLEMENTATION_PLAN.md` — M11 delivered scope and limits
- `docs/checkpoints/M11-vision-and-desktop-browser-control.md` — completion record and evaluation
- `milestone.md` — dashboard progress and next milestone

## Evaluation

Evaluation completed with fake Groq and MCP responses:

- `python -m compileall -q backend scripts tests` — passed
- `python -m scripts.verify_tool_policies` — passed with 16 configured tool bindings
- `python -m scripts.evaluate_vision` — passed: image validation, shared Groq vision request, task-scoped screenshot, permissions, action trace, screenshot-data redaction, and cancellation cleanup
- `python -m unittest tests.test_vision_pipeline` — 1 test passed
- `python -m scripts.evaluate_runtime_m00_m07` — passed
- `python -m scripts.evaluate_rag` — passed
- OpenAPI route check for both vision endpoints — passed

No live Groq request or real browser MCP server was used. A browser MCP command must be configured locally before the browser actions are available in a running EIVA instance.

## Completion checks

- [x] JPEG, PNG, and WebP images are validated and analyzed with the configured vision role.
- [x] Browser tools require a task ID and enabled per-tool permissions; write actions also require verified approval.
- [x] Browser actions emit task events; cancellation closes the task-owned MCP process, and screenshot bytes are removed from task persistence.

## Runtime notes

- Default vision model: `qwen/qwen3.8-27b`; change the `vision` role in `config/models.yaml` when needed.
- Default upload limit: 20 MB. Images are sent to Groq for analysis and are not stored by EIVA.
- `config/mcp_servers.yaml` remains empty until the local Playwright MCP command is configured. The runtime does not install or start a browser server automatically.
- The runtime approval callback/UI is not wired yet. Tools marked `requires_approval: true` are denied until one is configured; screenshot and tab listing are read-only.
- This milestone controls browser pages/tabs through semantic Playwright actions. Native Windows application-window enumeration and coordinate-based mouse input are not part of the current Playwright integration.

