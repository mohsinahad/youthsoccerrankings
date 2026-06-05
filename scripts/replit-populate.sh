#!/usr/bin/env bash
# One-time (or repeatable) data load: migrate, scrape one ECNL flight, recompute rankings.
# Usage: bash scripts/replit-populate.sh [EVENT] [FLIGHT] [AGE_GROUP] [GENDER]
# Defaults load the demo flight (ECNL U12 Boys, event 3210 / flight 26840).
set -euo pipefail

export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///./ysr.db}"
EVENT="${1:-3210}"
FLIGHT="${2:-26840}"
AGE="${3:-U12}"
GENDER="${4:-M}"

if command -v uv >/dev/null 2>&1; then RUN="uv run"; else RUN=""; fi

$RUN alembic upgrade head
$RUN ysr-scrape ecnl --event "$EVENT" --flight "$FLIGHT" --age-group "$AGE" --gender "$GENDER"
$RUN ysr-rank
echo "Populated ${DATABASE_URL} (event ${EVENT} flight ${FLIGHT}, ${AGE} ${GENDER})."
