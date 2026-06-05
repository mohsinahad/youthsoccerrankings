#!/usr/bin/env bash
# Replit run command: ensure a SQLite DB with an up-to-date schema, then serve the web app.
# Set this as your `.replit` run command:  run = "bash scripts/replit-run.sh"
set -euo pipefail

# Default to a file-based SQLite DB in the repo (persists on Replit's filesystem).
# Override DATABASE_URL (e.g. to a Postgres URL) to use a different database.
export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///./ysr.db}"

if command -v uv >/dev/null 2>&1; then RUN="uv run"; else RUN=""; fi

$RUN alembic upgrade head
exec $RUN uvicorn ysr.web.app:app --host 0.0.0.0 --port "${PORT:-8080}"
