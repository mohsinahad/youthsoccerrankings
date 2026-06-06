# Deploying to Replit

The web app is read-only and reuses the existing models. It works on **SQLite** (a file,
zero config) or **Postgres** (set `DATABASE_URL` — the app/alembic auto-add the `+psycopg`
driver, so Replit's managed Postgres URL works as-is).

## One-time setup

1. **Import the repo** into Replit (from GitHub).
2. **Set the run command** — in the `.replit` file:
   ```
   run = "bash scripts/replit-run.sh"
   ```
   This is **self-healing**: it puts uv on `PATH`, installs uv if missing, runs
   `uv sync --frozen` (rebuilds `.venv` with the right Python + the `ysr` package — a
   no-op when warm), then serves uvicorn on `0.0.0.0:${PORT:-8080}`. It does **not** run
   migrations (those belong to the populate step; the DB persists across FS wipes).
3. **Load data once** — in the Replit **Shell**:
   ```
   bash scripts/replit-populate.sh
   ```
   Defaults to demo event 3210 (Pre-ECNL, U9–U12 Boys, ~80 teams across 4 pools). It
   migrates, scrapes the whole event, and ranks. Pass an event id to load a different one:
   `bash scripts/replit-populate.sh 3210`.
4. **Run** and open the webview — the rankings page's pool selector shows each age/gender.

## Important Replit notes

- **Always go through `uv`.** Replit's system Python may be 3.11; this project needs 3.12.
  `uv` fetches 3.12 itself and installs `ysr` into `.venv`. Never run bare `python`/`uvicorn`
  (they hit system 3.11 with no `ysr` → `ModuleNotFoundError`). uv lives at
  `$HOME/workspace/.local/bin` (Replit's `/home/runner` is read-only).
- **Ephemeral filesystem = wipes.** Basic workspace / Autoscale clear installed packages
  between boots, so the venv vanishes. The self-healing run script re-syncs on boot
  (slower after a wipe, fast when warm). For startup that's both fast **and** reliable, use
  a **Reserved VM** deployment (persistent disk) — the recommended target for "always up."
- **Git on Replit:** never `git pull` or edit files there. Use
  `git fetch origin && git reset --hard origin/main` (Replit auto-commits cause conflicts).
- **Postgres:** Replit's managed Postgres sets `DATABASE_URL` (locked). It works unedited —
  the app normalizes `postgresql://` → `postgresql+psycopg://`. The DB persists across FS wipes.
- **Re-loading / updating data:** `replit-populate.sh` is idempotent — re-run anytime to
  refresh scores and rankings.
