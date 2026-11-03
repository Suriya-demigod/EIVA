"""Apply pending EIVA migrations and ensure the sqlite-vec index exists."""

from pathlib import Path

from backend.config import get_settings
from backend.database import Database
from backend.rag.repository import RagRepository


def main() -> None:
    settings = get_settings()
    database = Database(Path(settings.database_path))
    applied = database.initialize()
    RagRepository(database, settings.rag_embedding_dimension)
    print(f"database={database.path}")
    print(f"applied_migrations={applied}")
    print(f"known_migrations={database.applied_migrations()}")
    print(f"vector_index=rag_vectors_{settings.rag_embedding_dimension}")


if __name__ == "__main__":
    main()
