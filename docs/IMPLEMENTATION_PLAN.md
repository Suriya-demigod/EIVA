# EIVA complete implementation roadmap

This roadmap builds EIVA in working increments. Each phase ends with a usable, reviewable result before the next dependent phase begins.

Track current status and per-milestone file changes in the [milestone dashboard](../milestone.md). Each milestone checkpoint is maintained in `docs/checkpoints/`.

## Product and architecture decisions

- **Project:** EIVA, a modular personal AI assistant.
- **Model provider:** Groq only. No provider fallback or backup-provider layer.
- **Model selection:** Model IDs and role assignments remain configurable. Keep a small benchmark and re-run it when models/configuration change.
- **Integrations:** Add filesystem, GitHub, and Playwright tools behind permission checks. Do not add CST or antenna-project skills or MCP integrations.
- **Frontend:** Web UI for chat, tasks, agents, memory, voice, and vision capabilities as those backend features become available.
- **Secrets and data:** API keys stay in `.env`; never store them in source, logs, evaluation output, or commits.

## Build sequence

### 0. Foundation and model screening — complete

**Build:** Python project environment, FastAPI entry point, settings, Groq model router, configuration files, health route, evaluation script, and implementation notes.

**Complete when:** The app imports, configuration errors are clear, the health route responds, and the baseline benchmark can compare the configured Groq candidates without exposing secrets.

**Current state:** Complete. Scaffold, settings, health route, Groq router, and initial model screening are in place. The initial screening is only a baseline, not a final role decision.

### 1. API contracts and chat foundation

**Build:** Typed request/response schemas; chat, agent, task, and health routes; request validation; consistent error responses; request IDs; streaming response contract; API versioning.

**Complete when:** A client can submit a message, receive a response or stream, and get a useful error for invalid input, provider failure, or timeout.

**Current state:** Completed. Chat works through the Groq router with optional SSE; agent and task routes expose initial contracts and will connect to the registry/task manager in later milestones.

### 2. Model service and model evaluation

**Build:** Central Groq client lifecycle; configurable role routing for planner, researcher, developer, and reviewer; timeout/retry rules for transient failures; token and latency tracking; prompt/version records; evaluation dataset and report format.

**Complete when:** Every role can be assigned an allowed Groq model from configuration; evaluation runs the same tasks across candidates and records quality checks, latency, and usage; a human can inspect outputs before changing defaults. Do not use one aggregate heuristic score as the sole quality measure.

**Current state:** Completed. Groq timeouts/retries are bounded, model calls produce safe usage/latency telemetry, the client closes with the app lifecycle, and the versioned five-case evaluation ran against both configured candidates. Model-role assignments remain provisional because results tied on the small rubric.

### 3. Context and conversation management

**Build:** Conversation state, message history boundaries, context assembly, system instructions, truncation/summarization policy, and task-scoped context.

**Complete when:** Multi-turn conversations retain relevant context, stay within the selected model’s limits, and do not mix unrelated users or tasks.

**Current state:** M03 delivered bounded, task-scoped context and truncation behavior. M08 subsequently made conversation history durable in SQLite. The configured identity remains a single local user.

### 4. Agent base and registry

**Build:** Shared agent interface, agent configuration, registry, typed inputs/outputs, lifecycle/cancellation, and structured agent events.

**Complete when:** Agents can be loaded by name, invoked through a common interface, report progress, and fail without crashing the API process.

**Current state:** Shared typed agent contracts, YAML-backed definitions, registry registration/discovery, progress events, timeout handling, and cancellation hooks are implemented. The M00–M07 runtime evaluation passed progress, timeout, failure containment, and cancellation checks with fake agents. Concrete agents are implemented in M05. See the cross-milestone evaluation report.

### 5. Skill system and initial agents

**Build:** Skill manifest format, loader, validation, registry, and the initial web-research, code-debugging, GitHub-analysis, and document-analysis skills. Implement researcher, developer, browser, and reviewer agents using these skills.

**Complete when:** Skills are discoverable, validated, and attached only to suitable agents; an unknown or malformed skill is rejected with a clear error. Do not add CST or antenna-analysis skills.

**Current state:** Four validated skill manifests are loaded and assigned to researcher, developer, browser-planning, and reviewer agents. Unknown/malformed skills are rejected, and fake-router checks confirm prompts include only the assigned skills. The cross-milestone runtime evaluation passed; live Groq output was not repeated.

### 6. Permissions and tool integrations

**Build:** Permission policy, per-tool schemas, audit events, and adapters for filesystem, GitHub, and Playwright MCP servers. Separate read actions from writes and require approval for configured consequential actions.

**Complete when:** Each tool call is validated and authorized before execution, tool failures are contained, and side effects are visible in the task history. No CST MCP server is included.

**Current state:** Permission policies, strict per-tool schemas, path confinement, approval verification hooks, task-scoped audit records, and a lazy MCP stdio gateway are implemented for filesystem, GitHub, and Playwright actions. Policy checks and a fake local MCP stdio integration pass. `config/mcp_servers.yaml` remains empty until local server commands and credentials are configured. M07 connects audit events to task execution, and M08 makes them persistent.

### 7. Task manager, event bus, and orchestration

**Build:** Task lifecycle and status model; event bus; supervisor/planner; graph execution; handoffs; cancellation; research and coding workflows; bounded concurrency.

**Complete when:** A user request can be planned, routed to agents, use permitted tools, report progress, recover from a failed step where safe, and end with a clear result and trace.

**Current state:** At M07 completion, task lifecycle and event data were process-local. M08 subsequently persisted task lifecycle, events, and workflow checkpoints in SQLite. Research and coding task graphs, task-scoped tool audit handoffs, explicit tool-request routing, cancellation, and a four-task concurrency limit pass local async integration checks with fake agents. Real MCP servers remain unconfigured. See the M07 checkpoint.

### 8. Persistent storage and memory

**Build:** Database connection, migrations, repositories, conversation/task/checkpoint records, persistent short-term history, long-term memory, retrieval, and user controls for inspecting and deleting stored memories. The initial plan also considered automatic episodic/semantic extraction; M08 instead uses explicit memory capture to keep saved facts user-controlled. Automatic extraction remains deferred until its privacy behavior and evaluation criteria are specified.

**Complete when:** Data survives restarts, retrieval is scoped to the right user and task, migrations are repeatable, and memory can be inspected and removed through an authorized flow.

**Current state:** Complete for the explicit-capture scope. SQLite migrations and repositories persist scoped chat exchanges, task lifecycle/events/checkpoints, and user-saved memories. Memory search uses scoped lexical relevance; API routes support create, retrieve/list, inspect, and delete. M08 evaluation verifies restart behavior, scope separation, migration idempotence, task crash recovery, and memory deletion. Automatic episodic/semantic extraction is a documented deferral from the original broad scope, not an implemented feature.

### 9. Document and code RAG

**Build:** PDF/DOCX/text/code ingestion, structure-aware chunking, configurable local embeddings, SQLite `sqlite-vec` vector storage, FTS5 keyword search, RRF hybrid retrieval, and source citations. Keep all indexing local and send only retrieved excerpts through the existing Groq router. Reranking is intentionally excluded from the first version.

**Complete when:** EIVA can index supported files inside configured roots, retrieve relevant chunks, answer with source references, update or remove indexed material, and pass a small retrieval quality evaluation.

**Current state:** Complete for the supported formats. M09 provides path-confined PDF, DOCX, text, Markdown, and source-code ingestion; structure-aware overlapping chunks; configurable local BGE embeddings via FastEmbed/ONNX; SQLite `sqlite-vec` and FTS5 indexes; RRF retrieval; and Groq-grounded answers through the existing model router. Evaluation covers file loaders, semantic and keyword retrieval, migration preservation, metadata citations, scope, updates/removals, path confinement, and route behavior. Changing embedding dimensions requires re-indexing sources.

### 10. Voice interface

**Build:** Microphone capture, voice activity detection, speech-to-text, conversation coordination, text-to-speech, audio playback, and optional wake-word support behind explicit runtime settings.

**Complete when:** A user can speak a request, see/hear the response, interrupt or stop playback, and control microphone use clearly.

**Current state:** M10 provides a browser voice page with explicit microphone activation, silence-based submission, and stop/cancel controls. Audio transcription and WAV speech use the existing Groq model-router client; the transcript goes through the existing chat route and durable conversation history. Voice is disabled by default, audio input size and accepted types are bounded, and audio/transcript content is not logged or stored. The current endpoint accepts short speech synthesis requests (200 characters), so the page splits longer answers. Physical microphone/speaker behavior still needs a manual browser check on the target device; wake-word support remains optional and is deferred.

### 11. Vision and desktop/browser control

**Build:** Image input and vision analysis; screen capture; window discovery; mouse/keyboard action layer; browser session management; task-scoped computer-control permissions.

**Complete when:** EIVA can describe supplied images and perform only explicitly permitted computer actions, with a visible action trace and safe stop behavior.

**Current state:** M11 adds bounded JPEG/PNG/WebP question answering through a configurable Groq vision role and task-scoped Playwright MCP controls for browser tabs, screenshots, navigation, clicks, typing, and keys. Browser actions pass through existing schema validation, per-tool permissions, approval hooks, and task audit events. Cancelling a task terminates its task-owned browser MCP process; screenshot image bytes are excluded from task result persistence. The default MCP server configuration remains empty, and the approval checker/UI is not yet wired, so modifying browser actions stay denied until configured. Native Windows application windows and coordinate-level desktop input are outside this Playwright slice; the UI milestone can expose these API controls later.

### 12. Frontend application

**Build:** Chat panel, Jarvis core/status view, voice waveform, agent monitor, vision panel, memory panel, task monitor, settings, API services, state management, and responsive styling.

**Complete when:** The frontend supports chat and can show agent/task progress, errors, approvals, voice/vision status, and memory controls without relying on developer tools.

### 13. External agent communication

**Build:** Internal message types and bus first; then optional A2A server/client and agent card for explicitly configured external agents.

**Complete when:** Messages are authenticated, scoped, validated, traceable, and disabled unless configured. Local EIVA operation must not depend on external agents.

### 14. Observability, evaluation, and security hardening

**Build:** Structured logs, tracing, metrics, cost/token tracking, model/agent/tool evaluations, safety checks, failure injection, dependency review, and secret-handling review.

**Complete when:** A run can be traced end-to-end; model quality, latency, and cost are measurable; critical routes and workflows have automated coverage; sensitive values are absent from logs and reports; and failures produce actionable diagnostics.

### 15. Packaging, setup, and release readiness

**Build:** Setup scripts, local run commands, container configuration if needed, configuration reference, migration/backup guidance, and user-facing README.

**Complete when:** A clean environment can follow the documented steps to configure, start, use, and update EIVA without relying on undocumented local state.

## How we will evaluate EIVA

1. **Model screening:** Compare candidate Groq models on the same planning, coding, review, tool-selection, and response-quality cases. Record outputs, pass criteria, latency, and usage. Review failures manually before changing role mappings.
2. **Module checks:** Validate each module at its public boundary: schemas, storage, skill loading, permission decisions, tools, and frontend service integration.
3. **Workflow evaluations:** Run complete research and coding tasks, including tool errors, missing information, cancellation, and permission denial.
4. **Regression set:** Keep representative successful and failed cases versioned; rerun them when prompts, models, routing, or workflows change.
5. **Release gate:** No release until critical workflows pass, secrets are protected, and known limitations are documented.

## Working rules for each increment

For each phase: inspect the current code; implement the smallest complete slice; add or update its configuration and documentation; run the relevant checks; record results and limitations; then move to the next phase. Keep the system runnable throughout the build and avoid placeholder integrations that appear functional but do not work.
