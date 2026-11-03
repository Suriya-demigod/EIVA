"""Scoped lexical retrieval for explicitly stored memories."""

import re
from datetime import datetime, timezone

from backend.database.models import MemoryRecord


def _terms(text: str) -> set[str]:
    return {term.casefold() for term in re.findall(r"[\w'-]+", text) if len(term) > 1}


def rank_memories(query: str, memories: list[MemoryRecord], *, limit: int = 10) -> list[MemoryRecord]:
    query_terms = _terms(query)
    if not query_terms:
        return memories[:limit]
    now = datetime.now(timezone.utc)

    def score(memory: MemoryRecord) -> tuple[float, str]:
        content_terms = _terms(memory.content)
        tag_terms = _terms(" ".join(memory.tags))
        overlap = len(query_terms & content_terms)
        tag_overlap = len(query_terms & tag_terms)
        phrase_bonus = 2 if query.casefold() in memory.content.casefold() else 0
        if overlap == 0 and tag_overlap == 0 and phrase_bonus == 0:
            return 0.0, memory.created_at.isoformat()
        recency_days = max(0.0, (now - memory.created_at).total_seconds() / 86400)
        recency_bonus = max(0.0, 1.0 - recency_days / 365)
        relevance = overlap + tag_overlap * 2 + phrase_bonus + memory.importance * 0.1 + recency_bonus
        return relevance, memory.created_at.isoformat()

    return sorted((memory for memory in memories if score(memory)[0] > 1.0), key=score, reverse=True)[:limit]
