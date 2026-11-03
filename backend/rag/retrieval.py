"""User-scoped dense/FTS5 retrieval fused with Reciprocal Rank Fusion."""

from backend.rag.embeddings import LocalEmbedder
from backend.rag.models import RagChunk
from backend.rag.repository import RagRepository


class HybridRetriever:
    def __init__(self, repository: RagRepository, embedder: LocalEmbedder, *, candidate_k: int = 30,
                 rrf_k: int = 60) -> None:
        self.repository = repository
        self.embedder = embedder
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k

    def search(self, query: str, user_id: str, top_k: int = 6) -> list[tuple[RagChunk, float]]:
        if not query.strip():
            return []
        query_embedding = self.embedder.embed_query(query)
        vector_results = self.repository.search_vectors(user_id, query_embedding, self.candidate_k)
        keyword_results = self.repository.search_keywords(user_id, query, self.candidate_k)

        fused: dict[int, float] = {}
        for ranked in (vector_results, keyword_results):
            seen: set[int] = set()
            position = 0
            for item in ranked:
                chunk_id = item[0] if isinstance(item, tuple) else item
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                position += 1
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (self.rrf_k + position)
        ranked_ids = sorted(fused, key=lambda chunk_id: (-fused[chunk_id], chunk_id))[:top_k]
        chunks = self.repository.get_chunks(user_id, ranked_ids)
        return [(chunks[chunk_id], fused[chunk_id]) for chunk_id in ranked_ids if chunk_id in chunks]
