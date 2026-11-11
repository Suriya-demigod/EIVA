# EIVA configuration reference

Run commands from the repository root. EIVA reads environment variables and a private `.env` file in that directory. Variable names match the uppercase configuration field names below; they do not use an `EIVA_` prefix.

## Required secret

| Variable | Required | Purpose |
|---|---:|---|
| `GROQ_API_KEY` | Yes | Groq API access for chat, agents, vision, voice, and grounded RAG answers. Keep it only in `.env` or the process environment. |

Create `.env` locally, add `GROQ_API_KEY=<your key>` in a text editor, and save it in the repository root. `.env` is ignored by Git. Never paste its value into logs, reports, or issues.

## Application and provider

| Variable | Default | Notes |
|---|---|---|
| `APP_NAME` | `EIVA` | FastAPI title and health response service name. |
| `ENVIRONMENT` | `development` | Deployment/environment label. |
| `API_PREFIX` | `/api/v1` | Prefix for the application API routes. |
| `GROQ_TIMEOUT_SECONDS` | `45` | Provider request timeout; allowed range 0–300 (exclusive of 0). |
| `GROQ_MAX_RETRIES` | `2` | Groq client retry count; allowed range 0–5. |
| `MODELS_CONFIG_PATH` | `config/models.yaml` | Groq role and audio model mapping, plus optional token rates. |
| `AGENTS_CONFIG_PATH` | `config/agents.yaml` | Agent definitions and skill assignments. |
| `SKILLS_CONFIG_DIR` | `backend/skills/available` | Directory containing skill manifests. |
| `TOOL_BINDINGS_CONFIG_PATH` | `config/tool_bindings.yaml` | EIVA-to-MCP tool mapping. |
| `MCP_SERVERS_CONFIG_PATH` | `config/mcp_servers.yaml` | MCP server commands. |
| `PERMISSIONS_CONFIG_PATH` | `config/permissions.yaml` | Tool permissions and workspace roots. |

Model rates in `config/models.yaml` are optional USD per million tokens. They are not supplied by default; use rates from the account's applicable provider contract. Audio and streaming completion costs are not currently estimated.

## Context and storage

| Variable | Default | Notes |
|---|---|---|
| `LOCAL_USER_ID` | `local` | Scope used by this single-user local deployment. |
| `CONTEXT_MAX_INPUT_TOKENS` | `8192` | Approximate context budget, 512–32768. |
| `CONTEXT_MAX_COMPLETION_TOKENS` | `2048` | Maximum completion tokens, 128–8192. |
| `CONTEXT_MAX_HISTORY_MESSAGES` | `80` | Maximum retained conversation messages, 2–500. |
| `CONTEXT_MAX_CONVERSATIONS` | `512` | In-memory conversation lock limit, 1–10000. |
| `DATABASE_PATH` | `data/eiva.sqlite3` | SQLite database path. Startup applies pending migrations. |

## Local knowledge and embeddings

| Variable | Default | Notes |
|---|---|---|
| `RAG_ALLOWED_ROOTS` | `data/knowledge` | Allowed document roots. Separate multiple paths with `;` on Windows or `:` on POSIX. |
| `RAG_MAX_FILE_BYTES` | `2000000` | Maximum ingestible file size, 1 KiB–20 MB. |
| `RAG_CHUNK_CHARS` | `1100` | Target chunk length, 400–4000 characters. |
| `RAG_CHUNK_OVERLAP_CHARS` | `175` | Overlap, 0–500 and must be lower than the chunk size. |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model identifier; downloads on first use if uncached. |
| `RAG_EMBEDDING_DIMENSION` | `384` | Must match the selected embedding model. A dimension change requires a compatible database/index. |
| `RAG_EMBEDDING_CACHE_DIR` | `data/models` | Local model cache, excluded from Git. |
| `RAG_RETRIEVAL_TOP_K` | `6` | Final hybrid retrieval count, 5–8. |
| `RAG_CANDIDATE_K` | `30` | Candidate count for vector and keyword search, 8–100. |

The first RAG indexing or search operation may download the embedding model. Document processing, chunking, embeddings, and hybrid retrieval run locally.

## Optional voice and agent communication

| Variable | Default | Notes |
|---|---|---|
| `VOICE_ENABLED` | `false` | Enables the voice API/page; restart after changing. |
| `VOICE_MAX_AUDIO_BYTES` | `25000000` | Upload limit, 1 KiB–100 MB. |
| `VISION_MAX_IMAGE_BYTES` | `20000000` | Upload limit, 1 KiB–20 MB. |
| `A2A_ENABLED` | `false` | Enables the optional authenticated A2A server. |
| `A2A_SERVER_TOKEN` | unset | Required when A2A is enabled; at least 32 characters. Store privately. |
| `A2A_AGENT_NAME` | `EIVA` | Published Agent Card name. |
| `A2A_AGENT_DESCRIPTION` | `EIVA local personal assistant` | Published description. |
| `A2A_PUBLIC_URL` | `http://127.0.0.1:8000/a2a/v1` | Public URL must use HTTPS; loopback HTTP is allowed for local development. |
| `A2A_PEERS_CONFIG_PATH` | `config/a2a_peers.yaml` | Explicitly trusted outbound peer cards and token variable names. |

For outbound A2A, put each peer credential in the process environment or the private `.env` file under the name specified by that peer's `token_env`. Do not put token values in YAML. External MCP server commands and tool access are configured separately in `config/mcp_servers.yaml`, `config/tool_bindings.yaml`, and `config/permissions.yaml`.

## Other configuration files

| File | Controls |
|---|---|
| `config/models.yaml` | Groq role mappings, audio models, optional cost rates. |
| `config/agents.yaml` | Agent registry and workflow role configuration. |
| `backend/skills/available/` | Validated skill manifests and prompt instructions. |
| `config/mcp_servers.yaml` | Local MCP server commands; empty by default. |
| `config/tool_bindings.yaml` | EIVA tool names and MCP tool mappings. |
| `config/permissions.yaml` | Tool availability, workspace roots, and approval requirements. |
| `config/a2a_peers.yaml` | Explicitly trusted external A2A peers; empty by default. |

Configuration paths are relative to the repository root unless an absolute path is supplied.
