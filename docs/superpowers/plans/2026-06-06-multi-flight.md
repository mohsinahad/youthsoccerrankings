# Multi-Flight Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ysr-scrape ecnl --event <id>` ingests every active flight in an event, auto-deriving each flight's age-group + gender, with per-flight error isolation.

**Architecture:** Add event-tree fetch/parse to `scrapers/ecnl.py` (a pure `parse_event_flights` yielding `FlightRef`s with derived age/gender); rework the `ysr-scrape ecnl` CLI to loop those flights, reusing the existing `fetch_division`/`parse_division`/`ingest_games` per flight. Drop the manual `--age-group`/`--gender` args.

**Tech Stack:** Python 3.12, httpx, SQLAlchemy 2.0, pytest, argparse, stdlib `re`/`logging`. mypy --strict, ruff.

**Depends on:** Plans 1–3, 5 (merged). On branch `feat/multi-flight` (off `main`). The test fixture `tests/fixtures/ecnl_event_tree.json` (a trimmed real event tree: 2 boys divisions × 2 flights — U12 ×2, U11 ×2) is already committed.

**Environment:** `uv` at `~/.local/bin/uv` (not on PATH). Prefix uv commands: `export PATH="$HOME/.local/bin:$PATH" && uv run ...`. Verify each task with pytest + `uv run ruff check .` + `uv run mypy src tests`.

---

### Task 1: Event-tree fetch + parse (`FlightRef`)

**Files:**
- Modify: `src/ysr/scrapers/ecnl.py`
- Create: `tests/test_ecnl_event.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ecnl_event.py`:
```python
import json
import logging
import pathlib

import httpx
import pytest

from ysr.scrapers.ecnl import fetch_event_tree, parse_event_flights
from ysr.scrapers.http import HttpClient

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_tree.json"


def test_parse_event_flights_from_real_tree() -> None:
    tree = json.loads(FIXTURE.read_text())
    flights = parse_event_flights(tree)
    assert [f.flight_id for f in flights] == [26840, 26847, 26838, 26839]
    assert [f.age_group for f in flights] == ["U12", "U12", "U11", "U11"]
    assert all(f.gender == "M" for f in flights)


def test_parse_event_flights_gender_active_and_age_filters() -> None:
    tree = {
        "data": {
            "boysDivAndFlightList": [
                {
                    "divisionID": 1,
                    "divisionName": "B2013",
                    "flightList": [
                        {"flightID": 100, "flightName": "U12 (2013) North", "hasActiveSchedule": True},
                        {"flightID": 101, "flightName": "U12 (2013) Inactive", "hasActiveSchedule": False},
                        {"flightID": 102, "flightName": "Showcase only", "hasActiveSchedule": True},
                    ],
                }
            ],
            "girlsDivAndFlightList": [
                {
                    "divisionID": 2,
                    "divisionName": "G2013",
                    "flightList": [
                        {"flightID": 200, "flightName": "U12 (2013) Girls North", "hasActiveSchedule": True}
                    ],
                }
            ],
        }
    }
    by_id = {f.flight_id: f for f in parse_event_flights(tree)}
    assert set(by_id) == {100, 200}  # 101 inactive, 102 no U## -> excluded
    assert by_id[100].gender == "M" and by_id[100].age_group == "U12"
    assert by_id[200].gender == "F" and by_id[200].age_group == "U12"


def test_parse_event_flights_logs_skipped_flight(caplog: pytest.LogCaptureFixture) -> None:
    tree = {
        "data": {
            "boysDivAndFlightList": [
                {"flightList": [{"flightID": 9, "flightName": "no age here", "hasActiveSchedule": True}]}
            ],
            "girlsDivAndFlightList": [],
        }
    }
    with caplog.at_level(logging.WARNING):
        assert parse_event_flights(tree) == []
    assert "9" in caplog.text


def test_fetch_event_tree_raises_on_non_success() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"result": "error"}))
    client = HttpClient(client=httpx.Client(transport=transport), min_interval=0.0)
    with pytest.raises(RuntimeError, match="non-success"):
        fetch_event_tree(client, event_id=3210)
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_event.py -v` → FAIL (cannot import fetch_event_tree / parse_event_flights).

- [ ] **Step 3: Write minimal implementation** — edit `src/ysr/scrapers/ecnl.py`. Add `import re` and `from dataclasses import dataclass` to the imports at the top (keep existing imports). Add the `_AGE_RE` constant near `_BASE`, and add the `FlightRef` dataclass + the two functions (the existing `_BASE`, `logger`, `fetch_division`, `parse_division`, `_parse_match`, `_parse_date` stay as they are):
```python
import re
from dataclasses import dataclass

_AGE_RE = re.compile(r"U(\d+)")


@dataclass(frozen=True)
class FlightRef:
    flight_id: int
    age_group: str
    gender: str
    name: str


def fetch_event_tree(client: HttpClient, *, event_id: int) -> dict[str, Any]:
    url = f"{_BASE}/get-event-schedule-or-standings/{event_id}"
    payload = client.get_json(url)
    if payload.get("result") != "success":
        raise RuntimeError(
            f"AthleteOne API returned non-success for event {event_id}: "
            f"result={payload.get('result')!r} message={payload.get('message')!r}"
        )
    return payload


def parse_event_flights(tree: dict[str, Any]) -> list[FlightRef]:
    data = tree["data"]
    flights: list[FlightRef] = []
    for list_key, gender in (("boysDivAndFlightList", "M"), ("girlsDivAndFlightList", "F")):
        for division in data.get(list_key) or []:
            for flight in division.get("flightList") or []:
                if not flight.get("hasActiveSchedule"):
                    continue
                name = str(flight.get("flightName", ""))
                match = _AGE_RE.search(name)
                if match is None:
                    logger.warning(
                        "skipping flight %r: no age group (U##) in name %r",
                        flight.get("flightID"),
                        name,
                    )
                    continue
                flights.append(
                    FlightRef(
                        flight_id=int(flight["flightID"]),
                        age_group=f"U{match.group(1)}",
                        gender=gender,
                        name=name,
                    )
                )
    return flights
```
(`logger = logging.getLogger(__name__)` already exists in this file from the hardening pass. Add the `re`/`dataclass` imports in their correct alphabetical positions to satisfy ruff.)

- [ ] **Step 4: Verify** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_event.py -v` → 4 PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy src tests` → both clean.

- [ ] **Step 5: Commit**
```bash
git add src/ysr/scrapers/ecnl.py tests/test_ecnl_event.py
git commit -m "feat: fetch + parse ECNL event tree into FlightRefs (derive age/gender)"
```

---

### Task 2: Event-wide CLI rework + populate script

**Files:**
- Modify: `src/ysr/ingest.py` (add `EventIngestResult`)
- Modify: `src/ysr/cli.py` (rework the `ecnl` command — full replacement below)
- Modify: `tests/test_cli.py` (full replacement below)
- Modify: `scripts/replit-populate.sh` (whole-event load)

- [ ] **Step 1: Write the failing tests** — REPLACE the entire contents of `tests/test_cli.py` with:
```python
import json
import pathlib

import pytest
from sqlalchemy import func, select

from ysr.cli import main
from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Game, Source, Team

TREE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_tree.json"


def _migrate(db_url: str) -> None:
    create_all(make_engine(db_url))


def _fake_division(client: object, *, event_id: int, flight_id: int) -> dict[str, object]:
    # Distinct teams per flight so we can see multiple pools populate.
    home, away = flight_id * 10 + 1, flight_id * 10 + 2
    return {
        "data": [
            {
                "gameDate": "2026-03-01T10:00:00",
                "homeTeam": f"Home {flight_id}",
                "awayTeam": f"Away {flight_id}",
                "hometeamID": home,
                "awayteamID": away,
                "homeTeamClub": f"HC {flight_id}",
                "awayTeamClub": f"AC {flight_id}",
                "hometeamscore": 2,
                "awayteamscore": 1,
                "flight": f"flight {flight_id}",
            }
        ]
    }


@pytest.fixture()
def db_url(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+pysqlite:///{tmp_path / 'scrape.db'}"
    _migrate(url)
    monkeypatch.setenv("DATABASE_URL", url)
    tree = json.loads(TREE.read_text())
    monkeypatch.setattr("ysr.cli.fetch_event_tree", lambda *a, **k: tree)
    return url


def test_event_ingests_all_flights(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ysr.cli.fetch_division", _fake_division)
    assert main(["ecnl", "--event", "3210"]) == 0
    with make_session_factory(make_engine(db_url))() as s:
        assert s.scalar(select(func.count()).select_from(Game)) == 4  # 4 flights × 1 game
        assert s.scalar(select(func.count()).select_from(Team)) == 8  # 4 × 2 teams
        pools = {(ag, g) for ag, g in s.execute(select(Team.age_group, Team.gender).distinct()).all()}
        assert pools == {("U12", "M"), ("U11", "M")}
        src = s.scalar(select(Source).where(Source.name == "ECNL"))
        assert src is not None and src.status == "ok"


def test_single_flight_only(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ysr.cli.fetch_division", _fake_division)
    assert main(["ecnl", "--event", "3210", "--flight", "26840"]) == 0
    with make_session_factory(make_engine(db_url))() as s:
        assert s.scalar(select(func.count()).select_from(Game)) == 1
        assert s.scalar(select(func.count()).select_from(Team)) == 2


def test_flight_failure_is_isolated(
    db_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def flaky(client: object, *, event_id: int, flight_id: int) -> dict[str, object]:
        if flight_id == 26847:
            raise RuntimeError("boom")
        return _fake_division(client, event_id=event_id, flight_id=flight_id)

    monkeypatch.setattr("ysr.cli.fetch_division", flaky)
    assert main(["ecnl", "--event", "3210"]) == 0
    assert "1 failed" in capsys.readouterr().out
    with make_session_factory(make_engine(db_url))() as s:
        assert s.scalar(select(func.count()).select_from(Game)) == 3  # 3 of 4 flights succeeded


def test_errors_on_unmigrated_db(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'empty.db'}")
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        main(["ecnl", "--event", "3210"])
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -v` → FAIL (cannot import `EventIngestResult`; CLI lacks `--event`-only flow).

- [ ] **Step 3a: Add `EventIngestResult`** — in `src/ysr/ingest.py`, add after the existing `IngestResult` dataclass:
```python
@dataclass(frozen=True)
class EventIngestResult:
    flights_ingested: int
    flights_failed: int
    inserted: int
    updated: int
    unchanged: int
    teams_created: int
```

- [ ] **Step 3b: Replace `src/ysr/cli.py` entirely** with:
```python
from __future__ import annotations

import argparse
import logging

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ysr.db import make_engine, make_session_factory
from ysr.ingest import EventIngestResult, get_or_create_source, ingest_games, mark_source_run
from ysr.scrapers.ecnl import (
    FlightRef,
    fetch_division,
    fetch_event_tree,
    parse_division,
    parse_event_flights,
)
from ysr.scrapers.http import HttpClient

logger = logging.getLogger(__name__)

_REQUIRED_TABLES = ("sources", "games", "teams", "team_aliases")


def _ingest_flights(
    session: Session,
    source_id: int,
    client: HttpClient,
    event_id: int,
    flights: list[FlightRef],
) -> EventIngestResult:
    ingested = failed = inserted = updated = unchanged = teams = 0
    for flight in flights:
        try:
            payload = fetch_division(client, event_id=event_id, flight_id=flight.flight_id)
            games = parse_division(payload)
            result = ingest_games(
                session, source_id, games, age_group=flight.age_group, gender=flight.gender
            )
            session.commit()
            ingested += 1
            inserted += result.inserted
            updated += result.updated
            unchanged += result.unchanged
            teams += result.teams_created
        except Exception:
            session.rollback()
            failed += 1
            logger.warning("flight %s (%s) failed", flight.flight_id, flight.name, exc_info=True)
    return EventIngestResult(ingested, failed, inserted, updated, unchanged, teams)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ysr-scrape")
    sub = parser.add_subparsers(dest="source", required=True)
    ecnl = sub.add_parser("ecnl", help="Ingest ECNL flights for an event from AthleteOne/TGS")
    ecnl.add_argument("--event", type=int, required=True)
    ecnl.add_argument("--flight", type=int, default=None, help="optional: only this flight id")
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
        session.commit()  # persist source row so run status survives a later failure
        client = HttpClient()
        try:
            tree = fetch_event_tree(client, event_id=args.event)
            flights = parse_event_flights(tree)
            if args.flight is not None:
                flights = [f for f in flights if f.flight_id == args.flight]
            result = _ingest_flights(session, source.id, client, args.event, flights)
            mark_source_run(session, source, "ok")
            session.commit()
        except Exception:
            session.rollback()
            mark_source_run(session, source, "error")
            session.commit()
            raise

    print(
        f"event {args.event}: ingested {result.flights_ingested} flights "
        f"({result.flights_failed} failed) — {result.inserted} new, {result.updated} updated, "
        f"{result.unchanged} unchanged, {result.teams_created} teams"
    )
    return 0
```

- [ ] **Step 3c: Update `scripts/replit-populate.sh`** — replace its whole contents with:
```bash
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
```

- [ ] **Step 4: Verify** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -v` → 4 PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy src tests` → all clean. Also confirm `export PATH="$HOME/.local/bin:$PATH" && uv run ysr-scrape ecnl --help` shows `--event`/`--flight` (no age/gender), and `bash -n scripts/replit-populate.sh` passes.

- [ ] **Step 5: Commit**
```bash
git add src/ysr/ingest.py src/ysr/cli.py tests/test_cli.py scripts/replit-populate.sh
git commit -m "feat: event-wide multi-flight ingestion with per-flight isolation"
```

---

## Self-Review

**Spec coverage:** §3 derivation (gender by list, age via `U(\d+)`, active-only, skip+log unparseable) → Task 1 `parse_event_flights`. `fetch_event_tree` + envelope check → Task 1. §4 CLI rework (`--event` required, `--flight` optional, drop age/gender, per-flight try/except, summary) → Task 2 `main`/`_ingest_flights`. §4 populate script → Task 2 Step 3c. §5 `EventIngestResult` → Task 2 Step 3a. §6 error handling (top-level vs per-flight; commit-per-flight isolation) → Task 2 `_ingest_flights` (rollback-per-flight) + `main` (top-level mark error). §7 testing (parse fixture, gender/active/age filters, skip log, tree non-success, CLI all-flights/single/failure-isolation/unmigrated) → Tasks 1–2.

**Placeholder scan:** none — full code for functions, CLI, tests, and the script; exact commands.

**Type consistency:** `FlightRef(flight_id, age_group, gender, name)` defined Task 1, consumed in Task 2 (`_ingest_flights` loops `FlightRef`s, uses `.flight_id/.age_group/.gender/.name`). `fetch_event_tree(client, *, event_id)` / `parse_event_flights(tree)->list[FlightRef]` defined Task 1, called + monkeypatched in Task 2 (`ysr.cli.fetch_event_tree`). `EventIngestResult(flights_ingested, flights_failed, inserted, updated, unchanged, teams_created)` defined Task 2 Step 3a, built in `_ingest_flights`, fields used in the summary print. `ingest_games(session, source_id, games, *, age_group, gender)` / `get_or_create_source` / `mark_source_run` reused with their existing signatures. `fetch_division`/`parse_division` unchanged. The CLI test monkeypatches `ysr.cli.fetch_event_tree` and `ysr.cli.fetch_division` — both module-level imports in the rewritten `cli.py`.

**Note:** per-flight `session.commit()` makes each flight atomic, so a failing flight's `session.rollback()` only discards that flight (earlier flights already committed); the source row is committed up front so run-status survives.
