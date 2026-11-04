# EIVA

See [milestone.md](milestone.md) for the visual build dashboard, current progress, and links to milestone checkpoints.

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the full implementation roadmap.

Conversation history, tasks, workflow checkpoints, and explicitly saved memories use a local SQLite database at `data/eiva.sqlite3` by default. Migrations run at application startup; they can also be applied with `python -m scripts.migrate_db`. Database files are excluded from Git.

## Local knowledge base

By default, EIVA indexes files placed under `data/knowledge` (also excluded from Git). Configure additional allowed roots with `RAG_ALLOWED_ROOTS`; on Windows separate paths with `;`. Supported formats include PDF, DOCX, Markdown, text, Python, Ruby, JavaScript/TypeScript, JSON, YAML, TOML, SQL, and common source files. Files over `RAG_MAX_FILE_BYTES` are skipped. API paths are resolved inside configured roots.

The local embedding model is configurable with `RAG_EMBEDDING_MODEL` and defaults to `BAAI/bge-small-en-v1.5` (384 dimensions). FastEmbed runs it locally through ONNX Runtime and caches model files under `data/models`; the first indexing/search operation downloads the public model if it is not cached. No embedding API is used. The model cache and knowledge corpus are excluded from Git.

- `POST /api/v1/knowledge/index` with `{"path":"."}` indexes the default knowledge root; a relative file or child directory can also be given.
- `GET /api/v1/knowledge/sources` lists indexed sources; `DELETE /api/v1/knowledge/sources/{source_id}` removes one and its chunks.
- `POST /api/v1/knowledge/search` with `{"query":"..."}` returns ranked excerpts with source file and line citations.
- `POST /api/v1/knowledge/answer` returns a Groq answer grounded in retrieved excerpts and labeled citations.

Retrieval combines a local `sqlite-vec` dense-vector search with SQLite FTS5 keyword search using Reciprocal Rank Fusion. The answer endpoint sends only the top retrieved excerpts, with source labels and metadata, to the existing Groq model router. PDF citations include page numbers; text and code include line ranges; DOCX includes paragraph ranges and headings.

## Voice interface

The optional voice page is available at `/voice-ui/`. Voice is disabled by default; set `EIVA_VOICE_ENABLED=true` in your private `.env` and restart the API. The page requests microphone access only after the user selects **Start speaking**, detects a pause to submit the recording, and provides a **Stop / cancel** control for recording and playback.

Audio transcription and speech use Groq's audio endpoints through the same `AsyncGroq` client owned by EIVA's model router. The page sends the recording to Groq for transcription, submits the resulting text through the existing chat route, then requests WAV speech for the response. Audio and transcript content are not written to the EIVA database or logs. Use the voice controls only when you are comfortable sending the recording and spoken response text to Groq; provider account usage and charges apply.

Voice models and the default English voice are configured under `audio` in `config/models.yaml`. The browser splits generated responses into the current TTS endpoint's 200-character input limit. Microphone access requires a secure browser context (localhost or HTTPS). Optional wake-word detection is not enabled in this first version.

## Vision and browser control

`POST /api/v1/vision/analyze?question=...` accepts raw JPEG, PNG, or WebP bytes and returns a visual answer. Images are size limited by `VISION_MAX_IMAGE_BYTES` (20 MB maximum) and sent to the `vision` role in `config/models.yaml`, which defaults to Groq's `qwen/qwen3.8-27b` ([Groq vision docs](https://console.groq.com/docs/vision)). The uploaded image is not stored by EIVA.

`POST /api/v1/vision/screen` accepts `{"task_id":"...","question":"..."}`. It captures the current browser page through the task-scoped Playwright MCP connection, sends the screenshot to the vision model, and records start/completion events in that task's event stream. Screenshot bytes are removed from persisted task results.

The Playwright gateway exposes tab listing/selection, page screenshots, navigation, click, text entry, and key presses ([Playwright MCP reference](https://github.com/microsoft/playwright-mcp)). Every browser tool call requires a task ID. Read actions can run when their permission is enabled. Navigation, tab changes, clicks, typing, and key presses require verified approval; the app currently has no approval UI/checker, so these actions remain denied by default. Configure a local Playwright MCP command in `config/mcp_servers.yaml` to enable browser access. This milestone controls browser pages and tabs, not native Windows application windows or arbitrary screen coordinates. Vision analysis sends the supplied image or browser screenshot to Groq.
