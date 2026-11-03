# M06 — Permissions and tool integrations

**Status:** [x] Complete

## What this builds

Permission policies, schemas, audit events, and filesystem, GitHub, and Playwright MCP adapters.

## Files changed in this milestone

- `.env.example`
- `backend/config.py`
- `backend/core/permission_manager.py`
- `backend/lifecycle.py`
- `backend/mcp/client.py`
- `backend/tools/__init__.py`
- `backend/tools/gateway.py`
- `backend/tools/schemas.py`
- `config/mcp_servers.yaml`
- `config/permissions.yaml`
- `config/tool_bindings.yaml`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/checkpoints/M06-permissions-and-tool-integrations.md`
- `milestone.md`
- `scripts/verify_tool_policies.py`

## Evaluation

`python -m compileall -q backend scripts` and `python -m scripts.verify_tool_policies` passed. Checks cover nine typed tool bindings, allowed reads inside the workspace, path escape denial, approval-required writes, unknown actions, invalid filesystem/GitHub/Playwright arguments, and audit filtering by task ID. The M00–M07 runtime evaluation connected every binding to a fake local MCP stdio server: initialize/tool-call/close passed, read calls returned fixtures, the no-approval write was denied before execution, and fixture-approved write/browser actions reached only the fake server. An unconfigured server returned a contained `MCPUnavailableError`. No real MCP server, filesystem write, external account, or website was used.

## Completion checks

- [x] Tool arguments are validated before execution.
- [x] Permission decisions are enforced before side effects; consequential actions require a verified approval callback.
- [x] Tool outcomes create bounded, secret-safe audit records filterable by task ID, and tool errors are contained.
- [x] No CST MCP integration is included.

**Operational limits:** `config/mcp_servers.yaml` has no active commands; add locally installed MCP server commands and required environment variables before use. The app creates the gateway at startup and starts an MCP process only after a call passes schema and permission checks. Approval verification is an injected callback for the approval workflow milestone; without it, write and browser-action calls remain denied. Audit records are process-local until M08 persistence; M07 supplies task ID correlation and event history.

