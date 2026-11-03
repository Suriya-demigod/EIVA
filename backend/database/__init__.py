"""SQLite persistence and versioned schema migrations."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


class Database:
    def __init__(self, path: Path, migrations_dir: Path | None = None) -> None:
        self.path = path
        self.migrations_dir = migrations_dir or Path(__file__).parent / "migrations"
        self._sqlite_vec_enabled = False

    def enable_sqlite_vec(self) -> None:
        """Load sqlite-vec on each new connection for the hybrid RAG index."""
        self._sqlite_vec_enabled = True

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        if self._sqlite_vec_enabled:
            try:
                import sqlite_vec

                connection.enable_load_extension(True)
                sqlite_vec.load(connection)
            except (ImportError, sqlite3.Error, AttributeError) as exc:
                connection.close()
                raise RuntimeError("The sqlite-vec package is required for EIVA's hybrid RAG index") from exc
            finally:
                try:
                    connection.enable_load_extension(False)
                except sqlite3.Error:
                    pass
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> list[int]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        applied: list[int] = []
        with self.connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            connection.execute("PRAGMA journal_mode = WAL")
            known = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                version = int(migration.name.split("_", maxsplit=1)[0])
                if version in known:
                    continue
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in migration.read_text(encoding="utf-8").split(";"):
                        statement = statement.strip()
                        if statement:
                            connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, datetime('now'))",
                        (version, migration.name),
                    )
                    connection.commit()
                    applied.append(version)
                except Exception:
                    connection.rollback()
                    raise
        return applied

    def applied_migrations(self) -> list[tuple[int, str]]:
        with self.connection() as connection:
            rows = connection.execute("SELECT version, name FROM schema_migrations ORDER BY version").fetchall()
        return [(row[0], row[1]) for row in rows]
