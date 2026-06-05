# Scraper Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing ECNL scraper production-solid: clear API-error failure, per-record parse resilience, `Source` run tracking, and Alembic as the single schema source of truth.

**Architecture:** Targeted edits to the existing `ecnl.py` (fetch/parse), `ingest.py` (run tracking), and `cli.py` (schema pre-check + run lifecycle). No new modules. TDD throughout.

**Tech Stack:** Python 3.12, httpx, SQLAlchemy 2.0, pytest, argparse, stdlib `logging`. mypy --strict.

**Depends on:** Plans 1 & 2 (merged to `main`). On branch `feat/scraper-hardening` (already created off `main`).

**Environment:** `uv` at `~/.local/bin/uv` (not on PATH). Prefix every uv command: `export PATH="$HOME/.local/bin:$PATH" && uv run ...`.

---

### Task 1: API envelope check in `fetch_division`

**Files:**
- Modify: `src/ysr/scrapers/ecnl.py` (the `fetch_division` function)
- Modify: `tests/test_ecnl_fetch.py` (add a test)

- [ ] **Step 1: Write the failing test** — append to `tests/test_ecnl_fetch.py`:
```python
import pytest


def test_fetch_division_raises_on_non_success_body() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"result": "error", "message": "no such event"})
    )
    client = HttpClient(client=httpx.Client(transport=transport), min_interval=0.0)
    with pytest.raises(RuntimeError, match="non-success"):
        fetch_division(client, event_id=3210, flight_id=26840)
```
(Keep the existing `test_fetch_division_calls_endpoint_and_returns_payload`; the `import httpx`, `fetch_division`, and `HttpClient` imports are already at the top of the file.)

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_fetch.py -v` → the new test FAILS (no RuntimeError is raised yet).

- [ ] **Step 3: Implement** — in `src/ysr/scrapers/ecnl.py`, change `fetch_division` to validate the envelope before returning:
```python
def fetch_division(client: HttpClient, *, event_id: int, flight_id: int) -> dict[str, Any]:
    # teamID=0 returns every game in the flight (confirmed by the Task 1 spike).
    url = f"{_BASE}/get-schedules-by-flight/{event_id}/{flight_id}/0"
    payload = client.get_json(url)
    if payload.get("result") != "success":
        raise RuntimeError(
            f"AthleteOne API returned non-success for event {event_id} flight {flight_id}: "
            f"result={payload.get('result')!r} message={payload.get('message')!r}"
        )
    return payload
```

- [ ] **Step 4: Run tests to verify they pass** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_fetch.py -v` → both tests PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run mypy src tests` → "Success: no issues found".

- [ ] **Step 5: Commit**
```bash
git add src/ysr/scrapers/ecnl.py tests/test_ecnl_fetch.py
git commit -m "feat: fail clearly on non-success AthleteOne API body"
```

---

### Task 2: Per-record parse isolation in `parse_division`

**Files:**
- Modify: `src/ysr/scrapers/ecnl.py` (extract `_parse_match`, harden `parse_division`, add a module logger)
- Modify: `tests/test_ecnl_parse.py` (add a test)

- [ ] **Step 1: Write the failing test** — append to `tests/test_ecnl_parse.py`:
```python
import logging


def test_parse_division_skips_malformed_record_and_logs(caplog) -> None:  # type: ignore[no-untyped-def]
    good = {
        "gameDate": "2024-08-18T11:00:00",
        "homeTeam": "A",
        "awayTeam": "B",
        "hometeamID": 1,
        "awayteamID": 2,
        "homeTeamClub": "A Club",
        "awayTeamClub": "B Club",
        "hometeamscore": 3,
        "awayteamscore": 1,
        "flight": "U16 Boys",
    }
    # Played (scores present) but missing the required "homeTeam" key -> parse error, not an unplayed game.
    bad = {
        "gameDate": "2024-08-18T11:00:00",
        "awayTeam": "B",
        "hometeamID": 1,
        "awayteamID": 2,
        "hometeamscore": 3,
        "awayteamscore": 1,
        "flight": "U16 Boys",
        "matchID": 99999,
    }
    with caplog.at_level(logging.WARNING):
        games = parse_division({"data": [good, bad]})

    assert len(games) == 1
    assert games[0].home_team == "A"
    assert "99999" in caplog.text  # the malformed record's id was logged
```
(The `parse_division` import is already at the top of the file.)

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_parse.py -v` → the new test FAILS (currently a missing `homeTeam` raises `KeyError` out of `parse_division` instead of being skipped).

- [ ] **Step 3: Implement** — in `src/ysr/scrapers/ecnl.py`, add a module logger, extract `_parse_match`, and rewrite `parse_division` to isolate per-record failures. Add `import logging` to the imports, and add `logger = logging.getLogger(__name__)` near the top (after imports). Replace the existing `parse_division` with:
```python
def _parse_match(match: dict[str, Any]) -> ScrapedGame | None:
    home_score = match.get("hometeamscore")
    away_score = match.get("awayteamscore")
    if home_score is None or away_score is None:
        return None  # unplayed — skip, not an error
    return ScrapedGame(
        date=_parse_date(match["gameDate"]),
        home_source_id=str(match["hometeamID"]),
        home_team=match["homeTeam"],
        home_club=match.get("homeTeamClub"),
        away_source_id=str(match["awayteamID"]),
        away_team=match["awayTeam"],
        away_club=match.get("awayTeamClub"),
        home_score=int(home_score),
        away_score=int(away_score),
        competition=match.get("flight"),
        raw=match,
    )


def parse_division(payload: dict[str, Any]) -> list[ScrapedGame]:
    games: list[ScrapedGame] = []
    for match in payload["data"]:
        try:
            game = _parse_match(match)
        except Exception:
            logger.warning(
                "skipping malformed match %r", match.get("matchID"), exc_info=True
            )
            continue
        if game is not None:
            games.append(game)
    return games
```
(Keep the existing `_parse_date` helper. The existing `test_parse_division_maps_completed_games_only` test must still pass — the real fixture has no malformed records, so it returns 2 games as before.)

- [ ] **Step 4: Run tests to verify they pass** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_parse.py -v` → both tests PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run mypy src tests` → "Success: no issues found".

- [ ] **Step 5: Commit**
```bash
git add src/ysr/scrapers/ecnl.py tests/test_ecnl_parse.py
git commit -m "feat: isolate and log malformed records in parse_division"
```

---

### Task 3: `mark_source_run` in `ingest.py`

**Files:**
- Modify: `src/ysr/ingest.py` (add `mark_source_run`)
- Modify: `tests/test_ingest.py` (add a test)

- [ ] **Step 1: Write the failing test** — append to `tests/test_ingest.py`:
```python
def test_mark_source_run_sets_timestamp_and_status() -> None:
    from ysr.ingest import mark_source_run

    with _session() as s:
        src = get_or_create_source(s, "ECNL", "https://x", "ysr.scrapers.ecnl")
        mark_source_run(s, src, "ok")
        s.commit()

        assert src.status == "ok"
        assert src.last_run is not None
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ingest.py::test_mark_source_run_sets_timestamp_and_status -v` → FAIL (ImportError: cannot import name 'mark_source_run').

- [ ] **Step 3: Implement** — in `src/ysr/ingest.py`, add `import datetime as dt` to the imports (top of file, with the others) and add this function (e.g. just after `get_or_create_source`):
```python
def mark_source_run(session: Session, source: Source, status: str) -> None:
    # Source.last_run is a naive DateTime column; store naive UTC.
    source.last_run = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    source.status = status
    session.flush()
```

- [ ] **Step 4: Run tests to verify they pass** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ingest.py -v` → all PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run mypy src tests` → "Success: no issues found".

- [ ] **Step 5: Commit**
```bash
git add src/ysr/ingest.py tests/test_ingest.py
git commit -m "feat: add mark_source_run to record source run time and status"
```

---

### Task 4: CLI — schema pre-check (drop create_all) + run lifecycle

**Files:**
- Modify: `src/ysr/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests** — replace the entire contents of `tests/test_cli.py` with:
```python
import json
import pathlib

import pytest
from sqlalchemy import func, select

from ysr.cli import main
from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Game, Source

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def _migrate(db_url: str) -> None:
    # Tests own their schema setup now that the CLI no longer calls create_all.
    create_all(make_engine(db_url))


def test_main_ingests_flight_and_marks_ok(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"
    _migrate(db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)
    payload = json.loads(FIXTURE.read_text())
    monkeypatch.setattr("ysr.cli.fetch_division", lambda *a, **k: payload)

    rc = main(["ecnl", "--event", "3210", "--flight", "26840", "--age-group", "U12", "--gender", "M"])
    assert rc == 0

    with make_session_factory(make_engine(db_url))() as s:
        assert s.scalar(select(func.count()).select_from(Game)) == 2
        src = s.scalar(select(Source).where(Source.name == "ECNL"))
        assert src is not None and src.status == "ok" and src.last_run is not None


def test_main_errors_on_unmigrated_db(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'empty.db'}"  # no schema created
    monkeypatch.setenv("DATABASE_URL", db_url)
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        main(["ecnl", "--event", "3210", "--flight", "26840", "--age-group", "U12", "--gender", "M"])


def test_main_records_error_status_on_fetch_failure(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"
    _migrate(db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)

    def boom(*a: object, **k: object) -> dict[str, object]:
        raise RuntimeError("network down")

    monkeypatch.setattr("ysr.cli.fetch_division", boom)

    with pytest.raises(RuntimeError, match="network down"):
        main(["ecnl", "--event", "3210", "--flight", "26840", "--age-group", "U12", "--gender", "M"])

    with make_session_factory(make_engine(db_url))() as s:
        src = s.scalar(select(Source).where(Source.name == "ECNL"))
        assert src is not None and src.status == "error"
```

- [ ] **Step 2: Run tests to verify they fail** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -v` → failures (CLI still calls create_all and has no schema check / no run tracking).

- [ ] **Step 3: Implement** — replace the entire contents of `src/ysr/cli.py` with:
```python
from __future__ import annotations

import argparse

from sqlalchemy import inspect

from ysr.db import make_engine, make_session_factory
from ysr.ingest import get_or_create_source, ingest_games, mark_source_run
from ysr.scrapers.ecnl import fetch_division, parse_division
from ysr.scrapers.http import HttpClient

_REQUIRED_TABLES = ("sources", "games", "teams", "team_aliases")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ysr-scrape")
    sub = parser.add_subparsers(dest="source", required=True)
    ecnl = sub.add_parser("ecnl", help="Ingest one ECNL flight from AthleteOne/TGS")
    ecnl.add_argument("--event", type=int, required=True)
    ecnl.add_argument("--flight", type=int, required=True)
    ecnl.add_argument("--age-group", required=True)
    ecnl.add_argument("--gender", required=True, choices=["M", "F"])
    args = parser.parse_args(argv)

    engine = make_engine()
    existing = set(inspect(engine).get_table_names())
    missing = [t for t in _REQUIRED_TABLES if t not in existing]
    if missing:
        raise RuntimeError(
            f"database not initialized (missing tables: {', '.join(missing)}); "
            "run `alembic upgrade head`"
        )

    session_factory = make_session_factory(engine)
    with session_factory() as session:
        source = get_or_create_source(
            session, "ECNL", "https://www.totalglobalsports.com/ecnl/", "ysr.scrapers.ecnl"
        )
        session.commit()  # persist the source row so run status survives a later failure
        try:
            payload = fetch_division(HttpClient(), event_id=args.event, flight_id=args.flight)
            games = parse_division(payload)
            result = ingest_games(
                session, source.id, games, age_group=args.age_group, gender=args.gender
            )
            mark_source_run(session, source, "ok")
            session.commit()
        except Exception:
            session.rollback()
            mark_source_run(session, source, "error")
            session.commit()
            raise

    print(
        f"ingested: {result.inserted} new, {result.updated} updated, "
        f"{result.unchanged} unchanged, {result.teams_created} teams created"
    )
    return 0
```

- [ ] **Step 4: Run tests to verify they pass** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -v` → 3 PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q` (full suite green) and `export PATH="$HOME/.local/bin:$PATH" && uv run mypy src tests` → "Success: no issues found". Also confirm `export PATH="$HOME/.local/bin:$PATH" && uv run ysr-scrape --help` still prints usage.

- [ ] **Step 5: Commit**
```bash
git add src/ysr/cli.py tests/test_cli.py
git commit -m "feat: cli schema pre-check and source run tracking; drop create_all"
```

---

## Self-Review

**Spec coverage:** §3.1 envelope check → Task 1. §3.2 `_parse_match` + isolation + logging → Task 2. §3.3 `mark_source_run` + CLI try/except → Task 3 (helper) + Task 4 (lifecycle). §3.4 drop create_all + `inspect` schema pre-check + tests own schema setup → Task 4. Error-handling summary (§5) and testing (§6) all map to the four tasks' tests. Non-goals (multi-flight, rename) — not present. 

**Placeholder scan:** none — every step has full code and exact commands.

**Type consistency:** `fetch_division(client, *, event_id, flight_id) -> dict[str, Any]` signature unchanged (Task 1 only adds a body check), still called as such in Task 4 CLI and the existing/added tests. `parse_division(payload) -> list[ScrapedGame]` signature unchanged (Task 2). `_parse_match(match) -> ScrapedGame | None` introduced and used only within `ecnl.py` (Task 2). `mark_source_run(session, source, status)` defined Task 3, used in Task 4 CLI with the same signature. `ingest_games(...)` / `get_or_create_source(...)` calls in the Task 4 CLI match Plan 2's signatures. The CLI test's `_migrate` uses `create_all`/`make_engine` from `ysr.db` (both exist). `_REQUIRED_TABLES` names match the Alembic-created tables from Plan 1.

**Note on transactions (Task 4):** the source row is committed before the work block so that, on a failure, `mark_source_run(..., "error")` records the outcome after `session.rollback()` discards the partial ingest. `expire_on_commit=False` (set in `make_session_factory`) keeps the `source` instance usable across those commits/rollback.
