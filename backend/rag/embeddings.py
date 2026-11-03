"""Lazy local FastEmbed wrapper for configurable dense BGE embeddings."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from threading import Lock

logger = logging.getLogger("eiva.rag.embeddings")
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class LocalEmbeddingError(RuntimeError):
    pass


class LocalEmbedder:
    def __init__(self, model_name: str, dimensions: int, cache_dir: Path) -> None:
        self.model_name = model_name
        self.dimensions = dimensions
        self.cache_dir = cache_dir
        self._model = None
        self._lock = Lock()

    def _get_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                try:
                    from fastembed import TextEmbedding

                    logger.info("Loading local embedding model %s", self.model_name)
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    self._model = TextEmbedding(model_name=self.model_name, cache_dir=str(self.cache_dir))
                except Exception as exc:
                    raise LocalEmbeddingError(
                        f"Could not load local embedding model {self.model_name}; check model cache and FastEmbed setup"
                    ) from exc
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = [list(map(float, vector)) for vector in self._get_model().embed(texts)]
        except LocalEmbeddingError:
            raise
        except Exception as exc:
            raise LocalEmbeddingError("Local document embedding failed") from exc
        self._validate(vectors, len(texts))
        return vectors

    def embed_query(self, query: str) -> list[float]:
        try:
            model = self._get_model()
            query_text = QUERY_INSTRUCTION + query if self.model_name.casefold() == "baai/bge-small-en-v1.5" else query
            vector = list(map(float, next(iter(model.embed([query_text])))))
        except LocalEmbeddingError:
            raise
        except Exception as exc:
            raise LocalEmbeddingError("Local query embedding failed") from exc
        self._validate([vector], 1)
        return vector

    def _validate(self, vectors: list[list[float]], expected_count: int) -> None:
        if len(vectors) != expected_count or any(len(vector) != self.dimensions for vector in vectors):
            raise LocalEmbeddingError(
                f"Embedding output dimensions do not match RAG_EMBEDDING_DIMENSION={self.dimensions}"
            )
        for vector in vectors:
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                raise LocalEmbeddingError("Embedding model returned a zero-length vector")
            for index, value in enumerate(vector):
                vector[index] = value / norm
