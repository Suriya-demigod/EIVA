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
