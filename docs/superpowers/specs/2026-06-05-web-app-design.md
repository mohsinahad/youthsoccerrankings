# Web App (Plan 6) — Design Spec

**Date:** 2026-06-05
**Status:** Draft for review
**Depends on:** Plans 1–3, 5 (data layer, scraper, ranking engine).

## 1. Summary

The first user-facing surface: a read-only, server-rendered website that makes the
computed rankings visible, filterable, and shareable. It reuses the existing SQLAlchemy
models and reads the same Postgres the pipeline writes. MVP = a **rankings table** per
`(age_group, gender)` pool plus a **team page** per team. Confidence (rating deviation)
is surfaced throughout as the differentiator.

## 2. Goals & Non-Goals

### Goals
- Browse rankings for a pool: teams ordered by rating, with confidence and a provisional flag.
- A per-team page: header, key stats, rating trend, results — all from existing data.
- Server-rendered HTML with good per-page titles/meta for SEO.
- Reuse `ysr.models`/`ysr.db` (no schema duplication); one language, one Replit deploy.

### Non-Goals (this plan)
- Team comparison tool, accounts, Stripe/monetization (Plan 7).
- Writing/scraping/ranking (read-only site; data is produced by existing CLIs).
- New DB indexes / migrations (defer until data volume warrants).
- Scheduled recompute / automation.
- Heavy client-side JS framework (server-rendered; light enhancement only).

## 3. Stack & Architecture

**FastAPI + Jinja2, server-rendered.** A new read-only package `src/ysr/web/` that opens a
session via `ysr.db.make_session_factory` and reads through `ysr.models`. No new schema, no
writes. Served by `uvicorn` (the Replit run command).

Separation: **`queries.py`** holds pure-ish read functions (session in, typed result
dataclasses out); **`app.py`** holds routing + template rendering only; templates hold
presentation. This keeps data access testable independently of HTTP.

## 4. Routes

- `GET /` — landing: lists available pools (`list_pools()`) as links into the rankings page.
- `GET /rankings?age_group=<>&gender=<>` — the **Option A** rankings table for one pool:
  teams ordered by `rating` desc, tiebreak `rating_deviation` asc then `team_id` (stable
  order). Columns: rank, team (link), club, `rating` with `±` confidence, W-D-L; a
  "provisional" badge when `is_provisional`. Age/gender selectors set the query params.
  Sensible default pool if params omitted (first available).
- `GET /teams/{team_id}` — team page: header (display_name · club · age_group/gender) →
  key stats (national rank within its pool, `rating ±conf`, W-D-L record, provisional) →
  rating trend (points from `RatingHistory` ordered by `computed_at`) → results (each game:
  result W/D/L, opponent name, score, date, from `games`). Returns 404 for an unknown id.
- Each page sets a descriptive `<title>` and meta description (SEO).

## 5. Read Queries (`src/ysr/web/queries.py`)

Typed result dataclasses + functions (session as first arg):
- `list_pools(session) -> list[Pool]` — distinct `(age_group, gender)` among teams that
  have a rating, with team counts.
- `pool_rankings(session, age_group, gender) -> list[RankedTeam]` — join `Rating → Team`
  filtered to the pool, ordered by rating desc / RD asc / team_id; each `RankedTeam` carries
  rank, team_id, display_name, club, rating, rd, is_provisional, and W-D-L (computed from
  `games` where the team is home or away).
- `team_detail(session, team_id) -> TeamDetail | None` — team fields, its `RankedTeam` row
  (incl. rank within its pool), rating-history points, and a list of result rows
  (opponent display_name, our/their score, outcome, date) ordered most-recent first.

W-D-L and outcomes are derived from `games.home_score`/`away_score` relative to the team's
side. None is returned for a missing team (→ 404 in the route).

## 6. Components (files)

- `src/ysr/web/__init__.py`
- `src/ysr/web/queries.py` — read layer (above).
- `src/ysr/web/app.py` — FastAPI app, 3 routes, Jinja2 template rendering, a session
  dependency built from `make_engine`/`make_session_factory`.
- `src/ysr/web/templates/base.html`, `rankings.html`, `team.html`.
- `src/ysr/web/static/style.css` — clean, minimal baseline. **Implementation will use the
  frontend-design skill** for the actual visual quality.
- `pyproject.toml` — add `fastapi`, `jinja2`, `uvicorn` to dependencies.

## 7. Testing

FastAPI `TestClient` against a seeded in-memory SQLite DB (schema via `create_all`, seed
teams/games/ratings):
- `GET /rankings?...` → 200; teams listed in correct rating order; provisional badge present
  for a high-RD team; the `±` confidence renders; switching pool params changes the set.
- `GET /teams/{id}` → 200; shows the team's record and at least one result row; rank matches
  its position in the pool.
- `GET /teams/<unknown>` → 404.
- `GET /` → 200; lists the seeded pool(s).
- `queries.py` functions unit-tested directly (W-D-L math, ordering, missing team → None).
- Full suite + `ruff` + `mypy --strict` stay green.

## 8. Deployment (Replit)

Run command: `uvicorn ysr.web.app:app --host 0.0.0.0 --port $PORT`. Reads `DATABASE_URL`
(Replit Postgres in prod; the pipeline CLIs populate it). Schema is managed by Alembic as
before. Detailed Replit wiring is a thin follow-up once the app runs locally.

## 9. Success Criteria

- Visiting `/rankings` for a pool shows the real ranked table (rating + confidence +
  provisional), and clicking a team opens its page with record, rating trend, and results.
- Pages are server-rendered with descriptive titles (viewable source has the content — SEO).
- All reads reuse existing models; no schema change; tests + ruff + mypy green.
- Runs locally via `uvicorn` against a populated DB.

## 10. Out of Scope / Follow-ups

- Comparison tool; accounts + Stripe (Plan 7).
- `Team(age_group, gender)` and `Rating(rating)` indexes — add when pools get large
  (see [[web-app-considerations]]).
- Slug-based team URLs and richer SEO (sitemaps, structured data).
- Data breadth via multi-flight ingestion (Plan 4), run separately.
