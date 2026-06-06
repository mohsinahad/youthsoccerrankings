# Birth-Year Age Model (Plan 7) — Design Spec

**Date:** 2026-06-06
**Status:** Draft for review
**Depends on:** Plans 1–5 (data layer, scraper, multi-flight, ranking, web).

## 1. Summary

US youth soccer is organized by **birth year** (the fixed cohort identity); the "U##"
label is a *seasonal projection* that increments every season. Today we store the derived
U-age string (`Team.age_group = "U12"`), which is both the wrong canonical key and already
stale (the scraped "U12 (2013)" label was the 2024–25 season; in 2025–26 those 2013-borns
are U13). This plan makes **birth year canonical** — derive and store `Team.birth_year`,
key ranking pools on `(birth_year, gender)`, and **compute** the U-age label for display
from the current season so it auto-rolls each August.

## 2. Goals & Non-Goals

### Goals
- Store `Team.birth_year` (int) as the canonical age key; drop `Team.age_group`.
- Derive birth year reliably from TGS `divisionName` (`B2013`/`G2013` → 2013).
- Rank pools by `(birth_year, gender)`.
- Display label "U13 (2013 Boys)" where U-age is computed from the current season.
- Keep everything else (Glicko, identity, web structure) intact.

### Non-Goals
- Backfilling the existing stored data (it's re-scrapable — re-populate after migrating).
- Per-event/historical season handling (one "current season" derived from today's date).
- "Play-up" teams spanning age groups (still pinned to first-seen flight; tracked separately).

## 3. Age Rule (canonical)

- `season_end_year = today.year if today.month <= 7 else today.year + 1` (US Soccer
  seasonal year is Aug 1 – Jul 31).
- `u_age = season_end_year - birth_year`.
- Current (2025–26, ends 2026): 2014→U12, 2013→U13, 2012→U14. (See `memory/age-group-rule`.)

## 4. Derivation

`parse_event_flights` reads each division's `divisionName` and extracts the 4-digit birth
year (`re.search(r"(\d{4})", divisionName)` → `B2013`/`G2013` → 2013). `FlightRef` carries
`birth_year: int` instead of `age_group`. Gender still comes from the boys/girls list. A
division with no 4-digit year → its flights are skipped + logged. (We no longer parse the
`U##` from the flight name at all — it's the stale seasonal label.)

## 5. Model Change

`Team`: replace `age_group: Mapped[str]` with `birth_year: Mapped[int]` (other columns
unchanged). Regenerate the single initial Alembic migration (the project's established
pattern — data is re-scrapable; pre-1.0, no migration history to preserve). When the project
later holds irreplaceable data, switch to incremental migrations.

## 6. Component Changes

- **`scrapers/ecnl.py`:** `FlightRef.birth_year` (drop `age_group`); `parse_event_flights`
  derives it from `divisionName`.
- **`ingest.py`:** `_resolve_team(... birth_year: int ...)` creates `Team(birth_year=...)`;
  `ingest_games(session, source_id, games, *, birth_year, gender)`.
- **`cli.py`:** `_ingest_flights` passes `flight.birth_year`.
- **`ranking/engine.py`:** pools = distinct `(Team.birth_year, Team.gender)`; rank within
  each. (Glicko math unchanged.)
- **`web/season.py` (new):** pure `season_end_year(today=None) -> int` and
  `u_age(birth_year, today=None) -> int`.
- **`web/queries.py`:** `Pool(birth_year, gender, u_age, team_count)`;
  `pool_rankings(session, birth_year, gender)`; `team_detail` exposes `birth_year` + `u_age`.
- **`web/app.py`:** `/rankings?birth_year=<int>&gender=<M|F>` (default = first pool);
  index links by birth_year.
- **Templates:** show **"U{u_age} ({birth_year} Boys/Girls)"** in titles, the pool list, the
  filter `<select>` (option value = birth_year, text = the label), and team pages.

## 7. Replit Adoption (one-time, documented)

Because the live Postgres holds data under the old `age_group` schema and the initial
migration is regenerated, adopt by recreating the schema (demo data — re-scrapable):
```
# drop all ysr tables incl. alembic_version, then migrate + repopulate
uv run python -c "from sqlalchemy import text; from ysr.db import make_engine; e=make_engine();
import contextlib
with e.begin() as c:
    c.execute(text('DROP TABLE IF EXISTS alembic_version, ratings, rating_history, games, team_aliases, teams, sources CASCADE'))"
uv run alembic upgrade head
bash scripts/replit-populate.sh
```
(On SQLite, just delete the `.db` file instead.)

## 8. Testing

- `season.py`: `u_age(2013, date(2026,6,1)) == 13`, `u_age(2014, date(2026,6,1)) == 12`,
  and the Aug-1 rollover: `u_age(2013, date(2026,8,1)) == 14`.
- `parse_event_flights`: derives `birth_year` (2013/2014) from the committed event-tree
  fixture; a division with no year → skipped+logged.
- `ingest`: teams stored with `birth_year`; pools resolve by `(birth_year, gender)`.
- `ranking`: `recompute_all` rates per `(birth_year, gender)` pool (winner highest, etc.).
- `web`: rankings page filters by `birth_year`; page renders the "U13 (2013 Boys)" label;
  team page shows it; queries unit tests for the label.
- Full suite + `ruff` + `mypy --strict` green.

## 9. Success Criteria

- A 2013 cohort is stored as `birth_year=2013` and displays as **"U13 (2013 Boys)"** this
  season — and will read "U14" next season with no data change.
- Ranking pools and the web filter are keyed on birth year + gender.
- Re-populating after the migration yields correct pools/labels end-to-end.

## 10. Out of Scope / Follow-ups

- Identity update-on-match (so re-scrape refreshes `birth_year`/names without a DB reset) —
  would remove the recreate-DB step; deferred.
- Multi-season / historical rankings (one current season only).
- Cross-age "play-up" teams.
