"""Create a consistent SQLite backup, including committed WAL contents."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3


def backup_database(source_path: Path, destination_path: Path) -> Path:
    source = source_path.expanduser().resolve()
    destination = destination_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Database file does not exist: {source}")
    if source == destination:
        raise ValueError("Backup destination must be different from the source database")
    if destination.exists():
        raise FileExistsError(f"Backup destination already exists: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(source)) as source_connection:
            with closing(sqlite3.connect(destination)) as destination_connection:
                source_connection.backup(destination_connection)
                result = destination_connection.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise sqlite3.DatabaseError("Backup integrity check failed")
                destination_connection.commit()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.environ.get("DATABASE_PATH", "data/eiva.sqlite3")),
        help="SQLite database path (default: DATABASE_PATH or data/eiva.sqlite3)",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        help="Backup file path (default: timestamped file under data/backups)",
    )
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = args.destination or Path("data/backups") / f"eiva-{timestamp}.sqlite3"
    backup = backup_database(args.database, destination)
    print(f"Backup created: {backup}")


if __name__ == "__main__":
    main()
