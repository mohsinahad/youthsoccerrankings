# Ranking Engine (Plan 5) — Design Spec

**Date:** 2026-06-05
**Status:** Draft for review
**Depends on:** Plans 1–3 (data layer, scraper, hardening).

## 1. Summary

The first thing that turns ingested games into rankings: a Glicko-2 rating engine. It
recomputes, from scratch, a rating + confidence (rating deviation) for every team in each
`(age_group, gender)` pool from that pool's completed games, writing `Rating` rows and a
`RatingHistory` trail. Run via a new `ysr-rank` CLI. Confidence (RD) drives a `provisional`
flag — the honesty-about-uncertainty differentiator from the product spec.

## 2. Goals & Non-Goals

### Goals
- A typed, tested, dependency-free Glicko-2 implementation (Glickman's algorithm).
- Recompute all pools' ratings deterministically and idempotently from the games table.
- Persist `Rating` per team (rating, RD, volatility, provisional) and append `RatingHistory`.
- A `ysr-rank` command to run it; leave `ysr-scrape` untouched.

### Non-Goals (this plan)
- Weekly rating periods / RD time-decay for inactive teams (documented follow-up).
- Cross-pool or club-level ratings.
- Margin-of-victory weighting (future tuning).
- Any web/API surface (Plan 6) or scheduling/automation (thin later step).

## 3. Glicko-2 Core (`src/ysr/ranking/glicko2.py`, pure)

- A frozen value object `Glicko(rating: float = 1500.0, rd: float = 350.0, vol: float = 0.06)`.
- A pure function `rate(player: Glicko, results: list[tuple[Glicko, float]], *, tau: float = 0.5) -> Glicko`
  implementing one rating-period update per Glickman's paper: convert to the μ/φ scale,
  compute the estimated variance `v` and improvement `Δ`, solve the new volatility via the
  paper's iterative (Illinois-algorithm) procedure, then the new φ and μ; convert back.
  `score` ∈ {1.0 win, 0.5 draw, 0.0 loss}, from the player's perspective.
- A player with **no results** in a period gets only RD inflation:
  `rd' = sqrt(rd² + vol²)` (μ/φ unchanged). Exposed so the engine/future periods can use it.
- No I/O, no DB. `tau` (system constant) default 0.5.

**Test oracle:** Glickman's worked example — player `(1500, 200, 0.06)` vs opponents
`(1400, 30)`, `(1550, 100)`, `(1700, 300)` with results `1, 0, 0` → new ≈ `rating 1464.05`,
`rd 151.52`, `vol 0.05999`, asserted within a small tolerance.

## 4. Rating Period Model

**Single period, recompute from scratch (MVP).** Each run rebuilds every rating from the
default starting point using all of a pool's completed games as one rating period. This is
deterministic and idempotent (a full recompute). Opponent ratings within the period are the
default (everyone starts equal in a single-period batch), exactly as Glickman's single-period
example works. Weekly periods with RD decay are a future refinement and are out of scope here.

## 5. Schema Change: `Rating`

Drop `age_group` and `gender` from `Rating` and change its uniqueness to `(team_id)` — a
team has exactly one rating; pool is derived by joining to `Team`. New `Rating`:
`id`, `team_id` (unique FK), `rating`, `rating_deviation`, `volatility`, `is_provisional`,
`computed_at`. Delivered via a new Alembic migration. (`RatingHistory` is unchanged:
`team_id`, `rating`, `computed_at`.)

## 6. Engine (`src/ysr/ranking/engine.py`, DB I/O)

`recompute_all(session) -> RankingRunResult` (counts: pools, teams_rated, history_rows):
1. Find every distinct `(age_group, gender)` pool among teams that appear in games.
2. For each pool, load completed games between teams in that pool; for each team build its
   `results` list — opponent (default Glicko) + score from home/away scores
   (win 1 / draw 0.5 / loss 0).
3. `new = rate(Glicko(), results)` per team that played.
4. Upsert `Rating` by `team_id` (insert or update all fields); set
   `is_provisional = new.rd > PROVISIONAL_RD_THRESHOLD` (100.0); `computed_at = run time` (naive UTC).
5. Append a `RatingHistory(team_id, rating, computed_at)` row per rated team.

Pure rating math stays in `glicko2.py`; `engine.py` only does load → call → persist. Teams
in a pool with no completed games are skipped (no rating row).

## 7. CLI (`src/ysr/ranking/cli.py` + console script `ysr-rank`)

`ysr-rank` (no required args): schema pre-check via `inspect` (same "run `alembic upgrade
head`" error as `ysr-scrape`); open session; `recompute_all`; commit; print a summary
(`ranked N teams across M pools, wrote H history rows`); return 0. `ysr-scrape` is untouched.

## 8. Components Touched

- New: `src/ysr/ranking/__init__.py`, `glicko2.py`, `engine.py`, `cli.py`.
- Modify: `src/ysr/models.py` (`Rating`: drop two columns, change constraint).
- New Alembic migration for the `Rating` change.
- Modify: `pyproject.toml` (`[project.scripts]` add `ysr-rank`).
- Tests for each.

## 9. Testing

- **glicko2:** Glickman's worked example within tolerance; a no-results period inflates RD
  (`rd' = sqrt(rd²+vol²)`) and leaves rating unchanged; symmetry sanity (a clear winner ends
  rated above the loser).
- **engine (in-memory SQLite):** seed a pool with teams + completed games; `recompute_all`
  writes one `Rating` per team that played; the team that beat everyone ranks highest; a team
  with a single game is flagged `provisional` (high RD); a `RatingHistory` row is appended per
  team; re-running updates in place (no duplicate `Rating` rows) and appends new history.
- **CLI:** errors clearly on an unmigrated DB; on a seeded migrated temp DB writes ratings
  and returns 0.
- **migration:** autogenerated migration drops the two columns + adjusts the constraint;
  `upgrade`/`downgrade` run clean (verified on SQLite, dialect-agnostic).
- Full suite + `ruff` + `mypy --strict` stay green.

## 10. Success Criteria

- `ysr-rank` produces a Glicko-2 rating + RD + provisional flag for every team with games,
  per `(age_group, gender)` pool, idempotently.
- The Glicko-2 core matches the paper's worked example.
- `Rating` is normalized to one row per team; pool derived via `Team`.
- Rankings are queryable: order a pool's teams by `rating` desc via `Rating → Team` join.

## 11. Out of Scope / Follow-ups

- Weekly rating periods + RD time-decay for inactivity.
- Margin-of-victory weighting and `tau` tuning.
- Surfacing rankings in a UI/API (Plan 6) and scheduled recompute (later).
