# Deploying to Replit (SQLite — the simple path)

The MVP runs on a **SQLite file** — no separate database service, no `DATABASE_URL`
surgery. The web app is read-only; the scrape/rank CLIs write the file. Postgres remains
supported (just set `DATABASE_URL` to a Postgres URL — the app auto-adds the `+psycopg`
driver), but you don't need it to get live.

## One-time setup

1. **Import the repo** into Replit (from GitHub).
2. **Set the run command.** In the `.replit` file, set:
   ```
   run = "bash scripts/replit-run.sh"
   ```
   That script defaults `DATABASE_URL` to `sqlite+pysqlite:///./ysr.db`, runs migrations,
   and starts the web server on `0.0.0.0:${PORT:-8080}`.
3. **Load data once** — in the Replit **Shell**:
   ```
   bash scripts/replit-populate.sh
   ```
   (Defaults to the demo flight: ECNL U12 Boys, event 3210 / flight 26840. Pass
   `EVENT FLIGHT AGE_GROUP GENDER` to load a different one, e.g.
   `bash scripts/replit-populate.sh 3210 26840 U12 M`.)
4. **Click Run** and open the webview. You should see the rankings.

## Notes

- **Persistence:** the SQLite file lives in the repo's filesystem. On the Replit
  **workspace** and **Reserved VM** deployments this persists. On an **Autoscale**
  deployment the filesystem is ephemeral — for that target, either use a Reserved VM or
  commit/ship a pre-populated `ysr.db`.
- **`uv`:** the scripts use `uv run` if `uv` is available, otherwise they call the tools
  directly (relying on Replit having installed the project's dependencies from
  `pyproject.toml`). If neither works, install uv in the Shell:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **Re-loading data:** `replit-populate.sh` is idempotent — re-running updates scores and
  re-ranks without creating duplicates.
- **Switching to Postgres later:** set the `DATABASE_URL` secret to your Postgres URL
  (plain `postgresql://...` is fine — the app normalizes it). Everything else is unchanged.
