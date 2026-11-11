# EIVA

See [milestone.md](milestone.md) for the visual build dashboard, current progress, and links to milestone checkpoints.

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the full implementation roadmap.

## Quick start (Windows / PowerShell)

Requirements: Python 3.11 or newer, Git, and a Groq API key. Node.js is optional and only used for the frontend stream test; the application has no JavaScript build step.

```powershell
git clone https://github.com/Suriya-demigod/EIVA.git
Set-Location EIVA
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
if (-not (Test-Path .env)) { New-Item -ItemType File -Path .env | Out-Null }
notepad .env
```

In the private `.env` file, add `GROQ_API_KEY=<your Groq API key>` and save it. Do not commit or share `.env`. Start EIVA:

```powershell
& '.\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) and check [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health). The app creates the SQLite database and applies migrations at startup. The first RAG indexing/search can download the embedding model locally. For all settings and operational steps, see [Configuration](docs/CONFIGURATION.md) and [Operations](docs/OPERATIONS.md).

To run local release checks, use `powershell -ExecutionPolicy Bypass -File .\scripts\release_check.ps1`.

## Web application

Run EIVA with `uvicorn backend.main:app --reload` and open `http://127.0.0.1:8000/`. The workspace includes streaming chat, task progress and cancellation, task-scoped approval prompts, agent status, local knowledge search and citations, explicit memory controls, image analysis, and runtime settings. The standalone voice studio remains available at `/voice-ui/`.

The web app is served directly by FastAPI and uses native browser modules; it has no separate JavaScript build or package dependencies. Voice stays off unless `VOICE_ENABLED=true` is set. Consequential tool calls pause in the local approval queue and only continue after an explicit decision. Pending approvals are in memory and are cancelled when the app shuts down.

## Project structure

- `backend/` — API, model routing, agents, orchestration, tools, MCP client, memory, database, RAG, and skills.
- `backend/skills/available/` — validated YAML skill manifests loaded by the agent registry.
- `frontend/src/` — the FastAPI-served native-module workspace and `frontend/src/voice/` voice studio.
- `config/` — model, agent, permission, tool-binding, and optional external MCP server configuration.
- `data/` — local SQLite database, model cache, and knowledge documents; runtime data is excluded from Git.

The UI intentionally uses native JavaScript modules rather than React. There is no frontend package manifest or build step. MCP server implementations are installed/configured separately; EIVA connects through its shared client and `config/mcp_servers.yaml`.

## Agent-to-agent communication

Internal agents can publish validated messages through their task-scoped `AgentContext`. External A2A support is disabled unless `A2A_ENABLED=true` and a bearer token of at least 32 characters is set in `.env` as `A2A_SERVER_TOKEN`. Set `A2A_PUBLIC_URL` to the externally reachable HTTPS `/a2a/v1` endpoint before exposing the server.

The server publishes `/.well-known/agent-card.json`, accepts authenticated A2A 1.0 HTTP+JSON `POST /a2a/v1/message:send`, and exposes authenticated task status at `/a2a/v1/tasks/{task_id}`. A received text request starts a local research task. To contact a remote peer, add its Agent Card URL and an environment-variable name in `config/a2a_peers.yaml`, then call `POST /api/v1/agent-messages` with an existing `task_id`, the configured peer name, and the text to send. Peer credentials are resolved from the process environment or `.env`; credentials and message text are excluded from task trace events.

The initial A2A slice supports bounded text messages, bearer authentication, and task polling. Streaming, push notifications, attachments, and follow-up messages are not implemented. Peer endpoints must use HTTPS and share the configured Agent Card's origin; HTTP is accepted only for loopback development. See the [A2A Protocol Specification](https://github.com/a2aproject/A2A/blob/main/docs/specification.md).

Conversation history, tasks, workflow checkpoints, and explicitly saved memories use a local SQLite database at `data/eiva.sqlite3` by default. Migrations run at application startup; they can also be applied with `& '.\.venv\Scripts\python.exe' -m scripts.migrate_db`. Database files are excluded from Git. See [Operations](docs/OPERATIONS.md) for backup and restore steps.

## Local knowledge base

By default, EIVA indexes files placed under `data/knowledge` (also excluded from Git). Configure additional allowed roots with `RAG_ALLOWED_ROOTS`; on Windows separate paths with `;`. Supported formats include PDF, DOCX, Markdown, text, Python, Ruby, JavaScript/TypeScript, JSON, YAML, TOML, SQL, and common source files. Files over `RAG_MAX_FILE_BYTES` are skipped. API paths are resolved inside configured roots.

The local embedding model is configurable with `RAG_EMBEDDING_MODEL` and defaults to `BAAI/bge-small-en-v1.5` (384 dimensions). FastEmbed runs it locally through ONNX Runtime and caches model files under `data/models`; the first indexing/search operation downloads the public model if it is not cached. No embedding API is used. The model cache and knowledge corpus are excluded from Git.

- `POST /api/v1/knowledge/index` with `{"path":"."}` indexes the default knowledge root; a relative file or child directory can also be given.
- `GET /api/v1/knowledge/sources` lists indexed sources; `DELETE /api/v1/knowledge/sources/{source_id}` removes one and its chunks.
- `POST /api/v1/knowledge/search` with `{"query":"..."}` returns ranked excerpts with source file and line citations.
- `POST /api/v1/knowledge/answer` returns a Groq answer grounded in retrieved excerpts and labeled citations.

Retrieval combines a local `sqlite-vec` dense-vector search with SQLite FTS5 keyword search using Reciprocal Rank Fusion. The answer endpoint sends only the top retrieved excerpts, with source labels and metadata, to the existing Groq model router. PDF citations include page numbers; text and code include line ranges; DOCX includes paragraph ranges and headings.

## Voice interface

The optional voice page is available at `/voice-ui/`. Voice is disabled by default; set `VOICE_ENABLED=true` in your private `.env` and restart the API. The page requests microphone access only after the user selects **Start speaking**, detects a pause to submit the recording, and provides a **Stop / cancel** control for recording and playback.

Audio transcription and speech use Groq's audio endpoints through the same `AsyncGroq` client owned by EIVA's model router. The page sends the recording to Groq for transcription, submits the resulting text through the existing chat route, then requests WAV speech for the response. Audio and transcript content are not written to the EIVA database or logs. Use the voice controls only when you are comfortable sending the recording and spoken response text to Groq; provider account usage and charges apply.

Voice models and the default English voice are configured under `audio` in `config/models.yaml`. The browser splits generated responses into the current TTS endpoint's 200-character input limit. Microphone access requires a secure browser context (localhost or HTTPS). Optional wake-word detection is not enabled in this first version.

## Vision and browser control

`POST /api/v1/vision/analyze?question=...` accepts raw JPEG, PNG, or WebP bytes and returns a visual answer. Images are size limited by `VISION_MAX_IMAGE_BYTES` (20 MB maximum) and sent to the `vision` role in `config/models.yaml`, which defaults to Groq's `qwen/qwen3.8-27b` ([Groq vision docs](https://console.groq.com/docs/vision)). The uploaded image is not stored by EIVA.

`POST /api/v1/vision/screen` accepts `{"task_id":"...","question":"..."}`. It captures the current browser page through the task-scoped Playwright MCP connection, sends the screenshot to the vision model, and records start/completion events in that task's event stream. Screenshot bytes are removed from persisted task results.

The Playwright gateway exposes tab listing/selection, page screenshots, navigation, click, text entry, and key presses ([Playwright MCP reference](https://github.com/microsoft/playwright-mcp)). Every browser tool call requires a task ID. Read actions can run when their permission is enabled. Navigation, tab changes, clicks, typing, and key presses pause for a decision in the workspace approval queue. Configure a local Playwright MCP command in `config/mcp_servers.yaml` to enable browser access. This milestone controls browser pages and tabs, not native Windows application windows or arbitrary screen coordinates. Vision analysis sends the supplied image or browser screenshot to Groq.
