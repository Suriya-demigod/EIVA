"""M15 tests for consistent SQLite backup behavior."""

import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from scripts.backup_database import backup_database


class DatabaseBackupTests(unittest.TestCase):
    def test_backup_contains_committed_wal_data_and_passes_integrity_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "live.sqlite3"
            destination = root / "backups" / "snapshot.sqlite3"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE entries (value TEXT NOT NULL)")
                connection.execute("INSERT INTO entries VALUES ('committed in wal')")
                connection.commit()

            backup_database(source, destination)
            with closing(sqlite3.connect(destination)) as connection:
                self.assertEqual(connection.execute("SELECT value FROM entries").fetchone()[0], "committed in wal")
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_backup_refuses_missing_source_and_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                backup_database(root / "missing.sqlite3", root / "backup.sqlite3")
            source = root / "source.sqlite3"
            sqlite3.connect(source).close()
            destination = root / "backup.sqlite3"
            destination.write_bytes(b"preserve existing backup")
            with self.assertRaises(FileExistsError):
                backup_database(source, destination)
            self.assertEqual(destination.read_bytes(), b"preserve existing backup")


if __name__ == "__main__":
    unittest.main()
