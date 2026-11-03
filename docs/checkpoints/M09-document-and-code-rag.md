# M09 — Document and code Hybrid RAG

**Status:** [x] Complete

## What this builds

Local PDF, DOCX, text, Markdown, and source-code ingestion; structure-aware overlapping chunks; configurable BGE embeddings; SQLite `sqlite-vec` vectors and FTS5 keyword search; RRF hybrid retrieval; and citation-grounded answers through EIVA's existing Groq model router.

## Files changed in this milestone

- `.env.example` — local model, dimensions, cache, chunk, and retrieval settings
- `.gitignore` — excludes the local knowledge corpus and model weights
- `README.md` — installation, local model, supported formats, and API usage
- `requirements.txt` — FastEmbed/ONNX, `sqlite-vec`, PyPDF, and python-docx
- `backend/api/routes/knowledge.py` — hybrid index, source, search, delete, and answer routes
- `backend/api/schemas.py` — RAG request, source, hit, and citation fields
- `backend/config.py` — embedding, chunk, candidate, top-k, and cache settings
- `backend/database/__init__.py` — per-connection `sqlite-vec` extension loading
- `backend/database/migrations/003_hybrid_rag.sql` — document/chunk tables, FTS5 index, legacy index migration
- `backend/lifecycle.py` — RAG repository/service startup wiring
- `backend/rag/__init__.py`
- `backend/rag/chunking.py` — heading/declaration-aware chunks and overlap
- `backend/rag/embeddings.py` — lazy local BGE embeddings
- `backend/rag/loaders.py` — PDF, DOCX, text, Markdown, and source loaders
- `backend/rag/models.py` — document, segment, chunk, and source records
- `backend/rag/repository.py` — SQLite, FTS5, and sqlite-vec queries
- `backend/rag/retrieval.py` — dense/keyword Reciprocal Rank Fusion
- `backend/rag/service.py` — confined ingestion and retrieval orchestration
- `backend/knowledge/__init__.py` — removed superseded lexical package
- `backend/knowledge/chunking.py` — removed superseded lexical chunker
- `backend/knowledge/manager.py` — removed superseded indexing/retrieval manager
- `backend/knowledge/models.py` — removed superseded lexical records
- `backend/knowledge/repository.py` — removed superseded repository
- `backend/knowledge/retrieval.py` — removed superseded lexical ranker
- `backend/knowledge/vectors.py` — removed superseded sparse-vector helper
- `docs/IMPLEMENTATION_PLAN.md` — M09 architecture and completion notes
- `docs/checkpoints/M09-document-and-code-rag.md` — this checkpoint
- `scripts/evaluate_persistence.py` — expects migration 003 during M08 regression
- `scripts/evaluate_rag.py` — end-to-end hybrid RAG evaluation
- `scripts/smoke_local_rag_model.py` — actual local BGE + sqlite-vec semantic smoke check
- `scripts/migrate_db.py` — creates the configured sqlite-vec index after migrations
- `tests/__init__.py`
- `tests/test_rag_pipeline.py` — unittest entry for the local RAG integration suite
- Deleted legacy `backend/knowledge/` implementation modules after replacing that single implementation with `backend/rag/`

## Evaluation

Passed: `python -m compileall -q backend scripts tests`, `python -m scripts.evaluate_rag`, `python -m unittest tests.test_rag_pipeline`, `python -m scripts.smoke_local_rag_model`, `python -m scripts.evaluate_persistence`, `python -m scripts.evaluate_runtime_m00_m07`, and OpenAPI route registration. The integration suite uses temporary documents/databases, a deterministic fake embedder, and a fake Groq response while exercising real sqlite-vec and FTS5. The separate BGE smoke check loaded the cached `BAAI/bge-small-en-v1.5` model and retrieved the expected document first for a paraphrased query. No document content or API key was sent to an external service; only public model weights were downloaded into the ignored local cache. Migration 003 was applied to the local database and created `rag_vectors_384`.

## Completion checks

- [x] Required document formats load locally and preserve usable page/paragraph/line metadata.
- [x] Structure-aware chunks use the configured target and overlap; local BGE embeddings persist in sqlite-vec.
- [x] FTS5 and vector results fuse through RRF, remain user-scoped, and return the configured 5–8 results.
- [x] Re-index, deletion, migration, path confinement, citations, existing Groq router integration, and regression checks pass.

**Implementation boundary:** No reranker or OCR layer is included; image-only/scanned PDFs with no extractable text are skipped. DOCX citations use paragraph/table-row locations because pagination depends on a renderer. The default model cache is `data/models`; switching embedding dimensions creates a dimension-specific sqlite-vec table and existing documents need re-indexing to populate it. Only retrieved excerpts are included in Groq answer requests.
