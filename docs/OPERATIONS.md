# EIVA operations

Run the commands below from the repository root in PowerShell. Keep `.env`, SQLite files, backups, the RAG corpus, and the embedding cache private; they are local operational data and should not be committed.

## Start and stop

Start the development server:

```powershell
& '.\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Check `http://127.0.0.1:8000/health` for the API health response. Stop the foreground server with `Ctrl+C`. The server binds to loopback by default; use a reverse proxy with HTTPS and suitable access controls before exposing it beyond the local machine.

## Upgrade

1. Stop EIVA and back up the database (see below).
2. Pull or check out the intended repository revision.
3. Run `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1` to update the virtual environment from `requirements.txt`.
4. Start EIVA. Startup applies new numbered SQL migrations automatically. To apply and inspect migrations before startup, run `& '.\.venv\Scripts\python.exe' -m scripts.migrate_db`.
5. Check `/health`, then review server logs for startup/migration errors.

Keep a backup from the prior version until the updated version has been used successfully. SQLite migrations are forward-only; restore the pre-upgrade backup if a rollback is needed.

## Back up and restore SQLite

Create a consistent online backup with SQLite's backup API (it includes committed WAL data):

```powershell
& '.\.venv\Scripts\python.exe' -m scripts.backup_database
```

The default source is `DATABASE_PATH` or `data/eiva.sqlite3`; the default destination is a timestamped file under `data/backups/`. Choose another destination with `--destination`. Existing files are not overwritten. Keep backups outside Git and copy them to protected storage appropriate for the data they contain.

To restore, stop EIVA first. Preserve the current database, then copy the chosen backup to the configured database path. For the default path:

```powershell
Copy-Item -LiteralPath .\data\eiva.sqlite3 -Destination .\data\eiva-before-restore.sqlite3
Copy-Item -LiteralPath .\data\backups\eiva-YYYYMMDDTHHMMSSZ.sqlite3 -Destination .\data\eiva.sqlite3 -Force
```

Replace the timestamped filename with the backup to restore. Start EIVA and verify `/health`, conversation/task history, and knowledge retrieval as applicable. A changed embedding model or vector dimension can require re-indexing the local knowledge corpus.

## Local release checks

After setup, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\release_check.ps1
```

This runs unit and module evaluations, compilation, dependency consistency checks, and frontend stream tests when Node.js is available. It runs `pip-audit` if installed and warns when it is absent. The checks use local fixtures/mocks and do not call Groq or external MCP/A2A services. For provider model screening, run `& '.\.venv\Scripts\python.exe' -m scripts.evaluate_models`; this makes live Groq requests and consumes account usage.

## Operational boundaries

- One local user is assumed. This app does not currently provide multi-user authentication or an internet-facing deployment profile.
- Tool approvals are held in memory and are cancelled at shutdown. MCP servers are not installed or configured by default.
- External A2A support is disabled by default. Configure HTTPS peers and credentials before enabling it.
- SQLite database, knowledge files, and local model downloads live under `data/` by default and are Git-ignored.
- Voice and vision requests send user-selected audio/image content to Groq. Keep each feature disabled unless configured and appropriate for your use.
