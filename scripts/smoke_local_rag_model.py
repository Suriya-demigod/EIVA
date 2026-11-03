"""End-to-end local BGE + sqlite-vec semantic smoke check (downloads weights if absent)."""

from pathlib import Path
from tempfile import TemporaryDirectory

from backend.config import get_settings
from backend.database import Database
from backend.rag.embeddings import LocalEmbedder
from backend.rag.repository import RagRepository
from backend.rag.service import RagService


def main() -> None:
    settings = get_settings()
    with TemporaryDirectory(prefix="eiva-bge-smoke-") as temporary:
        base = Path(temporary)
        corpus = base / "knowledge"
        corpus.mkdir()
        relevant = corpus / "persistence.md"
        relevant.write_text(
            "The application initializes relational schema migrations before it writes any records.\n",
            encoding="utf-8",
        )
        for index, content in enumerate([
            "Tomato seedlings need sunlight, watering, and well-drained soil.",
            "Browser automation can locate buttons and fill form fields.",
            "A review checklist should identify correctness and maintainability issues.",
            "Voice activity detection identifies speech intervals in a microphone stream.",
            "The frontend displays task status, progress, and agent events.",
            "A cooking recipe lists ingredients and oven temperatures.",
            "Git branches isolate parallel development changes.",
        ]):
            (corpus / f"topic_{index}.txt").write_text(content, encoding="utf-8")

        database = Database(base / "smoke.sqlite3")
        database.initialize()
        repository = RagRepository(database, settings.rag_embedding_dimension)
        embedder = LocalEmbedder(
            settings.rag_embedding_model, settings.rag_embedding_dimension, Path(settings.rag_embedding_cache_dir)
        )
        service = RagService(repository, embedder, [corpus], chunk_chars=1_100, overlap_chars=175,
                             candidate_k=8, top_k=6)
        indexed = service.index_path(".", "smoke")
        assert len(indexed["indexed"]) == 8 and not indexed["skipped"]
        results = service.search("How does the application prepare its data structure before saving information?", "smoke")
        assert results and results[0][0].document_name == relevant.name, [
            (chunk.document_name, score) for chunk, score in results
        ]
        print("local_model=BAAI/bge-small-en-v1.5")
        print("local_dimensions=384")
        print(f"semantic_query_top_source={results[0][0].document_name}")
        print("sqlite_vec_semantic_retrieval=passed")


if __name__ == "__main__":
    main()
