#!/usr/bin/env bash
# One-time (or repeatable) data load: migrate, scrape a whole ECNL event, recompute rankings.
# Usage: bash scripts/replit-populate.sh [EVENT]
# Default loads the demo event (3210 — Pre-ECNL, multiple U10–U13 Boys flights).
set -euo pipefail

export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///./ysr.db}"
EVENT="${1:-3210}"

if command -v uv >/dev/null 2>&1; then RUN="uv run"; else RUN=""; fi

$RUN alembic upgrade head
$RUN ysr-scrape ecnl --event "$EVENT"
$RUN ysr-rank
echo "Populated ${DATABASE_URL} (event ${EVENT})."
