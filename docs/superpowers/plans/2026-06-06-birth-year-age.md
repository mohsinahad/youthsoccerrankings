# Birth-Year Age Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make birth year the canonical age key (`Team.birth_year`), derive it from TGS division names, rank pools by `(birth_year, gender)`, and display a season-computed U-age label like "U13 (2013 Boys)".

**Architecture:** A pure `season` util computes U-age from birth year + current date. A coordinated rename replaces `Team.age_group: str` with `Team.birth_year: int` across model, scraper derivation, ingest, ranking, and web, with the U-age computed for display only.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Alembic, FastAPI/Jinja2, pytest, stdlib `re`/`datetime`. mypy --strict, ruff.

**Depends on:** Plans 1–6 (merged). On branch `feat/birth-year-age` (off `main`). Note: the separate `fix/replit-run-selfheal` PR is unrelated (touches only `replit-run.sh`/deploy doc) and can merge independently.

**Environment:** `uv` at `~/.local/bin/uv` (not on PATH). Prefix uv commands: `export PATH="$HOME/.local/bin:$PATH" && uv run ...`. Verify with pytest + `uv run ruff check .` + `uv run mypy src tests`.

**Why only 2 tasks:** replacing the `age_group` column breaks model/ingest/ranking/web and all their tests simultaneously; a clean rename can't keep the suite green mid-way, so Task 2 is one atomic change. Task 1 (the `season` util) is genuinely independent and goes first.

---

### Task 1: Season / U-age util (pure)

**Files:**
- Create: `src/ysr/web/season.py`
- Create: `tests/test_season.py`

- [ ] **Step 1: Write the failing test** — `tests/test_season.py`:
```python
import datetime as dt

from ysr.web.season import season_end_year, u_age


def test_season_end_year_rolls_over_on_august() -> None:
    assert season_end_year(dt.date(2026, 6, 1)) == 2026   # Jun -> season ends 2026
    assert season_end_year(dt.date(2026, 7, 31)) == 2026  # Jul -> still 2025-26
    assert season_end_year(dt.date(2026, 8, 1)) == 2027   # Aug -> 2026-27


def test_u_age_current_season() -> None:
    today = dt.date(2026, 6, 1)  # 2025-26 season
    assert u_age(2014, today) == 12
    assert u_age(2013, today) == 13
    assert u_age(2012, today) == 14


def test_u_age_rolls_next_season() -> None:
    assert u_age(2013, dt.date(2026, 8, 1)) == 14  # new season -> +1
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_season.py -v` → FAIL (ModuleNotFoundError: ysr.web.season).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/web/season.py`:
```python
from __future__ import annotations

import datetime as dt


def season_end_year(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    # US Soccer seasonal year runs Aug 1 - Jul 31; it's labeled by the calendar year it ends.
    return today.year if today.month <= 7 else today.year + 1


def u_age(birth_year: int, today: dt.date | None = None) -> int:
    return season_end_year(today) - birth_year
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_season.py -v` → 3 PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy src tests` → clean.

- [ ] **Step 5: Commit**
```bash
git add src/ysr/web/season.py tests/test_season.py
git commit -m "feat: add season util to compute U-age from birth year"
```

---

### Task 2: Birth-year rename across model, scraper, ingest, ranking, web

This is one atomic change. Apply all edits, then run the full suite once at the end.

**Files (modify):** `src/ysr/models.py`, `src/ysr/scrapers/ecnl.py`, `src/ysr/ingest.py`, `src/ysr/cli.py`, `src/ysr/ranking/engine.py`, `src/ysr/web/queries.py`, `src/ysr/web/app.py`, `src/ysr/web/templates/index.html`, `src/ysr/web/templates/rankings.html`, `src/ysr/web/templates/team.html`, and tests: `tests/test_models.py`, `tests/test_ingest.py`, `tests/test_ranking_engine.py`, `tests/test_cli.py`, `tests/test_ecnl_event.py`, `tests/test_web_queries.py`, `tests/test_web_pages.py`. **Regenerate:** the Alembic initial migration.

- [ ] **Step 1: Model** — in `src/ysr/models.py`, in class `Team`, replace the `age_group` column line:
```python
    age_group: Mapped[str] = mapped_column(String)
```
with:
```python
    birth_year: Mapped[int] = mapped_column(Integer)
```
(`Integer` is already imported. `gender` and all other columns stay.)

- [ ] **Step 2: Scraper derivation** — in `src/ysr/scrapers/ecnl.py`: replace the `_AGE_RE` constant with `_YEAR_RE = re.compile(r"(\d{4})")`; change `FlightRef.age_group: str` to `birth_year: int`; rewrite `parse_event_flights` to derive birth year from `divisionName`:
```python
_YEAR_RE = re.compile(r"(\d{4})")


@dataclass(frozen=True)
class FlightRef:
    flight_id: int
    birth_year: int
    gender: str
    name: str


def parse_event_flights(tree: dict[str, Any]) -> list[FlightRef]:
    data = tree["data"]
    flights: list[FlightRef] = []
    for list_key, gender in (("boysDivAndFlightList", "M"), ("girlsDivAndFlightList", "F")):
        for division in data.get(list_key) or []:
            division_name = str(division.get("divisionName", ""))
            year_match = _YEAR_RE.search(division_name)
            if year_match is None:
                logger.warning("skipping division %r: no birth year in name", division_name)
                continue
            birth_year = int(year_match.group(1))
            for flight in division.get("flightList") or []:
                if not flight.get("hasActiveSchedule"):
                    continue
                flights.append(
                    FlightRef(
                        flight_id=int(flight["flightID"]),
                        birth_year=birth_year,
                        gender=gender,
                        name=str(flight.get("flightName", "")),
                    )
                )
    return flights
```
(`fetch_event_tree`, `fetch_division`, `parse_division`, `_parse_match`, `_parse_date` are unchanged.)

- [ ] **Step 3: Ingest** — in `src/ysr/ingest.py`: change `_resolve_team`'s `age_group: str` parameter to `birth_year: int` and the `Team(...)` construction from `age_group=age_group` to `birth_year=birth_year`; change `ingest_games`'s keyword param `age_group: str` to `birth_year: int` and pass `birth_year=birth_year` in both `_resolve_team` calls. Concretely, `_resolve_team` signature becomes:
```python
def _resolve_team(
    session: Session,
    source_id: int,
    source_team_id: str,
    name: str,
    club: str | None,
    birth_year: int,
    gender: str,
) -> tuple[Team, bool]:
```
its create line becomes:
```python
    team = Team(display_name=name, club=club, birth_year=birth_year, gender=gender)
```
and `ingest_games` becomes:
```python
def ingest_games(
    session: Session,
    source_id: int,
    games: list[ScrapedGame],
    *,
    birth_year: int,
    gender: str,
) -> IngestResult:
    ...
        home, home_new = _resolve_team(
            session, source_id, game.home_source_id, game.home_team, game.home_club, birth_year, gender
        )
        away, away_new = _resolve_team(
            session, source_id, game.away_source_id, game.away_team, game.away_club, birth_year, gender
        )
    ...
```
(The rest of `ingest_games` — the loop tallies and `_upsert_game` — is unchanged.)

- [ ] **Step 4: CLI** — in `src/ysr/cli.py`, in `_ingest_flights`, change the `ingest_games` call's keyword from `age_group=flight.age_group` to `birth_year=flight.birth_year`:
```python
            result = ingest_games(
                session, source_id, games, birth_year=flight.birth_year, gender=flight.gender
            )
```

- [ ] **Step 5: Ranking** — in `src/ysr/ranking/engine.py`, in `recompute_all`, change the pool query and loop from `age_group` to `birth_year`:
```python
    pools = session.execute(select(Team.birth_year, Team.gender).distinct()).tuples().all()
    ...
    for birth_year, gender in pools:
        team_ids = list(
            session.scalars(
                select(Team.id).where(Team.birth_year == birth_year, Team.gender == gender)
            ).all()
        )
```
(Everything else in `recompute_all` is unchanged — it only used the pool key to scope teams.)

- [ ] **Step 6: Web queries** — in `src/ysr/web/queries.py`: add `from ysr.web.season import u_age`; change the `Pool` and `TeamDetail` dataclasses and the three functions:
```python
@dataclass(frozen=True)
class Pool:
    birth_year: int
    gender: str
    u_age: int
    team_count: int


# RankedTeam unchanged.


@dataclass(frozen=True)
class TeamDetail:
    team: RankedTeam
    birth_year: int
    gender: str
    u_age: int
    history: list[HistoryPoint]
    results: list[ResultRow]


def list_pools(session: Session) -> list[Pool]:
    rows = (
        session.execute(
            select(Team.birth_year, Team.gender, func.count(Team.id))
            .join(Rating, Rating.team_id == Team.id)
            .group_by(Team.birth_year, Team.gender)
            .order_by(Team.birth_year, Team.gender)
        )
        .tuples()
        .all()
    )
    return [Pool(birth_year=by, gender=g, u_age=u_age(by), team_count=n) for by, g, n in rows]


def pool_rankings(session: Session, birth_year: int, gender: str) -> list[RankedTeam]:
    teams = list(
        session.scalars(
            select(Team).where(Team.birth_year == birth_year, Team.gender == gender)
        ).all()
    )
    # ... rest of the body is unchanged (ratings lookup, records, ordering, RankedTeam build) ...
```
and in `team_detail`, replace the `pool_rankings`/return with birth-year + u_age:
```python
    ranked = pool_rankings(session, team.birth_year, team.gender)
    ...
    return TeamDetail(
        team=me,
        birth_year=team.birth_year,
        gender=team.gender,
        u_age=u_age(team.birth_year),
        history=history,
        results=results,
    )
```

- [ ] **Step 7: Web app** — in `src/ysr/web/app.py`: add `from ysr.web.season import u_age as compute_u_age`; change the `rankings` route to use `birth_year`:
```python
@app.get("/rankings", response_class=HTMLResponse)
def rankings(
    request: Request,
    session: SessionDep,
    birth_year: int | None = None,
    gender: str | None = None,
) -> HTMLResponse:
    pools = queries.list_pools(session)
    teams: list[queries.RankedTeam] = []
    selected_u_age: int | None = None
    if pools:
        if birth_year is None or gender is None:
            birth_year, gender = pools[0].birth_year, pools[0].gender
        teams = queries.pool_rankings(session, birth_year, gender)
        selected_u_age = compute_u_age(birth_year)
    return templates.TemplateResponse(
        request,
        "rankings.html",
        {
            "pools": pools,
            "teams": teams,
            "birth_year": birth_year,
            "gender": gender,
            "u_age": selected_u_age,
        },
    )
```
(`index` and `team` routes are unchanged — `list_pools`/`team_detail` now carry the new fields.)

- [ ] **Step 8: Templates** — update the three templates:

`src/ysr/web/templates/index.html` (the pool list `<li>`):
```html
  {% for p in pools %}
  <li><a href="/rankings?birth_year={{ p.birth_year }}&gender={{ p.gender }}">U{{ p.u_age }} ({{ p.birth_year }} {{ "Boys" if p.gender == "M" else "Girls" }})</a> <span class="muted">({{ p.team_count }} teams)</span></li>
  {% endfor %}
```

`src/ysr/web/templates/rankings.html` (replace the title, `<h1>`, and the filter `<form>`; the table body is unchanged):
```html
{% block title %}{% if birth_year %}U{{ u_age }} ({{ birth_year }} {{ "Boys" if gender == "M" else "Girls" }}){% endif %} Rankings{% endblock %}
{% block content %}
<h1>{% if birth_year %}U{{ u_age }} ({{ birth_year }} {{ "Boys" if gender == "M" else "Girls" }}){% endif %} Rankings</h1>
<form method="get" action="/rankings" class="filters">
  <select name="birth_year">
    {% for p in pools|unique(attribute='birth_year') %}
    <option value="{{ p.birth_year }}" {{ "selected" if p.birth_year == birth_year else "" }}>U{{ p.u_age }} ({{ p.birth_year }})</option>
    {% endfor %}
  </select>
  <select name="gender">
    <option value="M" {{ "selected" if gender == "M" else "" }}>Boys</option>
    <option value="F" {{ "selected" if gender == "F" else "" }}>Girls</option>
  </select>
  <button type="submit">View</button>
</form>
```

`src/ysr/web/templates/team.html` (the pool line under the `<h1>`):
```html
<p class="muted">{{ d.team.club or "" }} · U{{ d.u_age }} ({{ d.birth_year }} {{ "Boys" if d.gender == "M" else "Girls" }})</p>
```
(and the `{% block title %}`/`{% block description %}` in team.html: replace `{{ d.age_group }} {{ "Boys" if d.gender == "M" else "Girls" }}` with `U{{ d.u_age }} ({{ d.birth_year }} {{ "Boys" if d.gender == "M" else "Girls" }})`.)

- [ ] **Step 9: Update all tests** — replace `age_group="U##"` with `birth_year=<int>` everywhere a `Team(...)` is constructed, and update the call/assert sites. Apply these per file:
  - `tests/test_models.py`: `Team(..., age_group="U15", ...)` → `Team(..., birth_year=2010, ...)`.
  - `tests/test_ingest.py`: every `Team(age_group="U16"...)` → `birth_year=2013`; the sibling-teams test's two cohorts → distinct birth years (e.g. 2013 and 2011); every `ingest_games(..., age_group="U16", gender="M")` → `birth_year=2013, gender="M"` (use 2011 where the test used "U14").
  - `tests/test_ranking_engine.py`: `Team(age_group="U16"...)` → `birth_year=2013`; the empty-pool team `age_group="U10"` → `birth_year=2016`.
  - `tests/test_ecnl_event.py`: in `test_parse_event_flights_from_real_tree`, assert `[f.birth_year for f in flights] == [2013, 2013, 2014, 2014]` (was the U12/U11 asserts) and keep the gender/flight_id asserts; in the filters test, the synthetic divisions already have `divisionName` "B2013"/"G2013" so assert `by_id[100].birth_year == 2013` / `by_id[200].birth_year == 2013`; replace the "no U## in name" skip test with a division whose `divisionName` has no 4-digit year (e.g. `{"divisionName": "Boys", "flightList": [...]}`) and assert it's skipped + logged.
  - `tests/test_cli.py`: the multi-flight test asserts pools — change `{("U12", "M"), ("U11", "M")}` to `{(2013, "M"), (2014, "M")}` and query `Team.birth_year` instead of `Team.age_group`.
  - `tests/test_web_queries.py`: `Team(age_group="U16"...)` → `birth_year=2013`; `pool_rankings(s, "U16", "M")` → `pool_rankings(s, 2013, "M")`; `list_pools` asserts `pools[0].birth_year == 2013` and (using a fixed clock isn't needed — just assert `pools[0].u_age == season_end_year(date.today()) - 2013` OR assert `birth_year`/`team_count` only); `team_detail` asserts `d.birth_year == 2013`.
  - `tests/test_web_pages.py`: `Team(age_group="U16"...)` → `birth_year=2013`; `client.get("/rankings", params={"birth_year": 2013, "gender": "M"})`; assert the body contains `2013`.

  (For any test asserting on `u_age`, import `from ysr.web.season import u_age` and compute the expected value rather than hard-coding, so it doesn't break next season.)

- [ ] **Step 10: Regenerate the migration**
```bash
export PATH="$HOME/.local/bin:$PATH"
rm alembic/versions/*_initial_schema.py
DATABASE_URL="sqlite+pysqlite:///./_regen.db" uv run alembic revision --autogenerate -m "initial schema"
```
Open the new migration and CONFIRM the `teams` table has `birth_year` (Integer) and NO `age_group`; all six tables present. Then verify up/down:
```bash
DATABASE_URL="sqlite+pysqlite:///./_regen.db" uv run alembic upgrade head
DATABASE_URL="sqlite+pysqlite:///./_regen.db" uv run alembic downgrade base
rm -f _regen.db
```

- [ ] **Step 11: Verify everything**
```bash
export PATH="$HOME/.local/bin:$PATH"
uv run pytest -q && uv run ruff check . && uv run mypy src tests
```
Expected: full suite green, ruff clean, mypy clean. Also confirm the live shape end-to-end:
```bash
rm -f _by.db
DATABASE_URL="sqlite+pysqlite:///./_by.db" uv run alembic upgrade head >/dev/null
DATABASE_URL="sqlite+pysqlite:///./_by.db" uv run ysr-scrape ecnl --event 3210 >/dev/null
DATABASE_URL="sqlite+pysqlite:///./_by.db" uv run ysr-rank
DATABASE_URL="sqlite+pysqlite:///./_by.db" uv run python -c "from ysr.db import make_engine, make_session_factory; from ysr.models import Team; from sqlalchemy import select, func; s=make_session_factory(make_engine())(); print(sorted({(by,g) for by,g in s.execute(select(Team.birth_year, Team.gender).distinct()).all()}))"
rm -f _by.db
```
Expected: pools printed as birth years, e.g. `[(2013, 'M'), (2014, 'M'), (2015, 'M'), (2016, 'M')]`.

- [ ] **Step 12: Commit**
```bash
git add -A
git commit -m "feat: birth-year canonical age model with season-computed U-age label"
```

---

## Self-Review

**Spec coverage:** §3 age rule → Task 1 `season.py`. §4 derivation (birth year from `divisionName`) → Task 2 Step 2. §5 model change + migration regen → Steps 1, 10. §6 components: scraper→Step 2, ingest→Step 3, cli→Step 4, ranking→Step 5, season→Task 1, queries→Step 6, app→Step 7, templates→Step 8. §8 testing (season rollover, derivation, ingest pools, ranking pools, web filter + label) → Task 1 tests + Step 9. §7 Replit adoption is operational (documented separately for the deploy, not code). Non-goals (backfill, multi-season, play-up) untouched.

**Placeholder scan:** Step 6 and Step 9 say "rest is unchanged" / give per-file edit instructions rather than reproducing whole unchanged files — each names the exact symbol/line to change with the new code, which is complete enough to apply unambiguously. No TBD/TODO.

**Type consistency:** `FlightRef(flight_id, birth_year:int, gender, name)` (Step 2) consumed in `cli._ingest_flights` via `flight.birth_year` (Step 4). `ingest_games(..., *, birth_year:int, gender)` (Step 3) called with `birth_year=` in cli (Step 4) and tests (Step 9). `Pool(birth_year, gender, u_age, team_count)` / `pool_rankings(session, birth_year:int, gender)` / `TeamDetail(..., birth_year, gender, u_age, ...)` (Step 6) used by app (Step 7) and templates (Step 8) and tests (Step 9). `u_age`/`season_end_year` (Task 1) imported in queries (Step 6) and app (Step 7). `Team.birth_year:int` (Step 1) used in ranking pool query (Step 5), queries (Step 6), migration (Step 10), and all Team constructions in tests (Step 9). The rankings template filter uses Jinja's `unique(attribute='birth_year')` filter (built-in).
