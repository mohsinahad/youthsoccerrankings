#!/usr/bin/env bash
# Replit run command (self-healing): ensure uv + deps exist, then serve the web app.
# Set this as your `.replit` run command:  run = "bash scripts/replit-run.sh"
#
# Replit's basic/Autoscale filesystem is ephemeral, so the venv can vanish between boots.
# This script re-ensures it via uv (which also pins the right Python from pyproject), so a
# wiped environment self-heals instead of falling back to a bare system Python. Migrations
# are NOT run here — they belong to the populate/deploy step (scripts/replit-populate.sh);
# the database (Postgres) persists across filesystem wipes, so the schema is already there.
set -euo pipefail

# uv installs into the writable workspace on Replit (~/.config is read-only there).
export PATH="$HOME/workspace/.local/bin:$HOME/.local/bin:$PATH"
export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///./ysr.db}"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Builds .venv (correct Python + the ysr package) if missing; a near-instant no-op when warm.
uv sync --frozen

exec uv run uvicorn ysr.web.app:app --host 0.0.0.0 --port "${PORT:-8080}"
