# ECNL Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest one ECNL division's teams and completed games from Total Global Sports (TGS) into the Postgres data layer, idempotently, via a runnable `ysr-scrape` CLI command.

**Architecture:** A source-agnostic normalized record (`ScrapedGame`) flows `fetch (TGS JSON via httpx) → parse (pure) → ingest (scoped team identity resolution + idempotent game upsert)`. Fetch (I/O) is isolated from parse (pure) so parsing is unit-tested against a committed fixture with no network. Ingest reuses Plan 1's `ysr.identity` and `ysr.models`.

**Tech Stack:** Python 3.12, httpx (HTTP client), SQLAlchemy 2.0 (existing), rapidfuzz (existing, via `ysr.identity`), pytest, argparse. Tooling: ruff, black, mypy --strict (all already configured).

**Depends on:** Plan 1 (Foundation & Data Layer). Execute on a branch off `feat/foundation-data-layer` (or off `main` once Plan 1 is merged). Add `httpx` to dependencies (Task 2).

**Note on the discovery spike (Task 1):** TGS's exact endpoint paths and JSON field names are confirmed by Task 1, which captures a real response as the test fixture. Tasks 3+ assert on the normalized `ScrapedGame` output, so if real TGS field names differ from the representative ones shown here, only the field-access lines inside `parse_division`/`fetch_division` and the committed fixture change — the tests and the `ScrapedGame` contract do not.

---

### Task 1: Discovery spike — capture a real TGS fixture and confirm the API shape

**Goal:** De-risk by confirming the live TGS endpoint(s), required headers, and JSON shape for one ECNL division, and commit a trimmed real response as the parser test fixture.

**Files:**
- Create: `tests/fixtures/ecnl_event_sample.json` (trimmed real TGS response)
- Create: `docs/superpowers/notes/ecnl-tgs-fieldmap.md` (the confirmed API URL + field map)

- [ ] **Step 1: Find a current ECNL division event.** On `https://public.totalglobalsports.com` browse to an active ECNL event's schedules/standings (one age group + gender, e.g. an ECNL Boys U16 conference). Note the numeric event/division identifiers in the URL.

- [ ] **Step 2: Capture the schedule/results JSON.** Use the browser DevTools Network tab: reload the schedules/standings view and find the XHR/fetch request that returns the match list as JSON (the TGS API call, e.g. on the `...execute-api.us-east-1.amazonaws.com/ProdStage` host). Save that response. (If working headlessly: attempt `httpx` against the discovered URL with browser-like headers `User-Agent`/`Accept: application/json`/`Origin: https://public.totalglobalsports.com`; if hard-blocked, capture via the browser and paste the JSON.)

- [ ] **Step 3: Trim and commit the fixture.** Reduce the captured JSON to ~3 matches that include **at least one completed game (both scores present) and one unplayed game (no scores)**, preserving the original structure/field names. Save as `tests/fixtures/ecnl_event_sample.json`.

- [ ] **Step 4: Record the field map.** In `docs/superpowers/notes/ecnl-tgs-fieldmap.md`, document: the exact request URL/method/headers; the JSON path to the list of matches; and the field names for home team name, away team name, home score, away score, game date, division/flight name, and the completed/played flag. Note any difference from the representative names used in this plan (`matches[]`, `homeTeamName`, `awayTeamName`, `homeTeamScore`, `awayTeamScore`, `gameDate`, `flightName`, `isComplete`).

- [ ] **Step 5: Commit.**
```bash
git add tests/fixtures/ecnl_event_sample.json docs/superpowers/notes/ecnl-tgs-fieldmap.md
git commit -m "spike: capture real ECNL/TGS schedule fixture and field map"
```

**Verification:** the fixture file parses as valid JSON and contains both a completed and an unplayed match; the field map names the JSON path and the seven fields above. If the captured field names differ from the representative ones, the implementer of Tasks 3 & 5 must use the **real** names (and may rename the fixture's fields only if they also adjust the parser to match — the fixture must stay structurally faithful to TGS).

---

### Task 2: Add httpx dependency and the normalized record

**Files:**
- Modify: `pyproject.toml` (add `httpx` to `dependencies`)
- Create: `src/ysr/scrapers/__init__.py`
- Create: `src/ysr/scrapers/base.py`
- Create: `tests/test_scraped_game.py`

- [ ] **Step 1: Write the failing test** — `tests/test_scraped_game.py`:
```python
import datetime as dt

from ysr.scrapers.base import ScrapedGame


def test_scraped_game_is_frozen_and_holds_fields() -> None:
    g = ScrapedGame(
        date=dt.date(2026, 3, 2),
        home_team="Strikers FC 2010 Boys",
        away_team="Surf SC 2010 Boys",
        home_score=3,
        away_score=1,
        competition="ECNL Boys U16",
        raw={"matchID": 1},
    )
    assert g.home_team == "Strikers FC 2010 Boys"
    assert g.home_score == 3
    import dataclasses

    assert dataclasses.is_dataclass(g)
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_scraped_game.py -v` → FAIL (ModuleNotFoundError: ysr.scrapers.base).

- [ ] **Step 3: Add httpx + create the module.** Add `"httpx>=0.27"` to the `dependencies` array in `pyproject.toml` (keep the existing entries). Create `src/ysr/scrapers/__init__.py` (empty). Create `src/ysr/scrapers/base.py`:
```python
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScrapedGame:
    date: dt.date
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    competition: str | None
    raw: dict[str, Any]
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_scraped_game.py -v` → PASS. Then `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add pyproject.toml uv.lock src/ysr/scrapers/__init__.py src/ysr/scrapers/base.py tests/test_scraped_game.py
git commit -m "feat: add httpx dep and ScrapedGame normalized record"
```

---

### Task 3: Parser — TGS JSON → list[ScrapedGame]

**Files:**
- Create: `src/ysr/scrapers/ecnl.py`
- Create: `tests/test_ecnl_parse.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ecnl_parse.py` (loads the committed fixture and asserts normalized output; only completed games are returned):
```python
import datetime as dt
import json
import pathlib

from ysr.scrapers.ecnl import parse_division

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def test_parse_division_returns_only_completed_games() -> None:
    payload = json.loads(FIXTURE.read_text())
    games = parse_division(payload)

    # Fixture contains one completed and one unplayed match; only the completed one is parsed.
    assert all(g.home_score is not None and g.away_score is not None for g in games)
    assert len(games) >= 1

    g = games[0]
    assert isinstance(g.date, dt.date)
    assert isinstance(g.home_team, str) and g.home_team
    assert isinstance(g.away_team, str) and g.away_team
    assert isinstance(g.home_score, int) and isinstance(g.away_score, int)
    assert g.raw  # original record preserved
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_parse.py -v` → FAIL (ModuleNotFoundError: ysr.scrapers.ecnl).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/scrapers/ecnl.py` (use the field names confirmed by the Task 1 field map; the representative names below match the representative fixture):
```python
from __future__ import annotations

import datetime as dt
from typing import Any

from ysr.scrapers.base import ScrapedGame

# Field names per the Task 1 TGS field map. Update these if the real fixture differs.
_MATCHES_KEY = "matches"
_HOME_NAME = "homeTeamName"
_AWAY_NAME = "awayTeamName"
_HOME_SCORE = "homeTeamScore"
_AWAY_SCORE = "awayTeamScore"
_DATE = "gameDate"
_FLIGHT = "flightName"


def _parse_date(value: str) -> dt.date:
    return dt.datetime.fromisoformat(value).date()


def parse_division(payload: dict[str, Any]) -> list[ScrapedGame]:
    games: list[ScrapedGame] = []
    for match in payload[_MATCHES_KEY]:
        home_score = match.get(_HOME_SCORE)
        away_score = match.get(_AWAY_SCORE)
        if home_score is None or away_score is None:
            continue  # unplayed — skip
        games.append(
            ScrapedGame(
                date=_parse_date(match[_DATE]),
                home_team=match[_HOME_NAME],
                away_team=match[_AWAY_NAME],
                home_score=int(home_score),
                away_score=int(away_score),
                competition=match.get(_FLIGHT),
                raw=match,
            )
        )
    return games
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_parse.py -v` → PASS. Then `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add src/ysr/scrapers/ecnl.py tests/test_ecnl_parse.py
git commit -m "feat: parse TGS division payload into ScrapedGame list"
```

---

### Task 4: HTTP client — httpx with headers, rate-limit, retry

**Files:**
- Create: `src/ysr/scrapers/http.py`
- Create: `tests/test_http_client.py`

- [ ] **Step 1: Write the failing test** — `tests/test_http_client.py` (uses httpx MockTransport; monkeypatches sleep so retry/backoff is instant):
```python
import httpx
import pytest

from ysr.scrapers.http import HttpClient


def test_get_json_returns_parsed_body() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))
    client = HttpClient(client=httpx.Client(transport=transport), min_interval=0.0)
    assert client.get_json("https://example.test/api") == {"ok": True}


def test_get_json_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ysr.scrapers.http.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval=0.0)
    assert client.get_json("https://example.test/api") == {"ok": True}
    assert calls["n"] == 2


def test_get_json_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ysr.scrapers.http.time.sleep", lambda _s: None)
    transport = httpx.MockTransport(lambda req: httpx.Response(503))
    client = HttpClient(client=httpx.Client(transport=transport), min_interval=0.0)
    with pytest.raises(RuntimeError):
        client.get_json("https://example.test/api", retries=3)
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_http_client.py -v` → FAIL (ModuleNotFoundError: ysr.scrapers.http).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/scrapers/http.py`:
```python
from __future__ import annotations

import time
from typing import Any, cast

import httpx

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://public.totalglobalsports.com",
}


class HttpClient:
    def __init__(self, *, client: httpx.Client | None = None, min_interval: float = 1.0) -> None:
        self._client = client or httpx.Client(headers=_DEFAULT_HEADERS, timeout=30.0)
        self._min_interval = min_interval
        self._last_request = 0.0

    def get_json(self, url: str, *, retries: int = 3) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(retries):
            self._respect_rate_limit()
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                return cast(dict[str, Any], resp.json())
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"GET {url} failed after {retries} attempts") from last_exc

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_http_client.py -v` → PASS (3 tests). Then `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add src/ysr/scrapers/http.py tests/test_http_client.py
git commit -m "feat: add rate-limited, retrying httpx json client"
```

---

### Task 5: fetch_division — wire the HTTP client to the TGS endpoint

**Files:**
- Modify: `src/ysr/scrapers/ecnl.py` (add `fetch_division` + the URL builder)
- Create: `tests/test_ecnl_fetch.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ecnl_fetch.py` (MockTransport returns the committed fixture; asserts fetch+parse round-trips):
```python
import json
import pathlib

import httpx

from ysr.scrapers.ecnl import fetch_division, parse_division
from ysr.scrapers.http import HttpClient

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def test_fetch_division_calls_tgs_and_returns_payload() -> None:
    body = json.loads(FIXTURE.read_text())
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json=body)

    client = HttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval=0.0)
    payload = fetch_division(client, event_id=2040, division_id=11501)

    assert "2040" in captured["url"] and "11501" in captured["url"]
    assert parse_division(payload)  # downstream parse works on the fetched payload
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_fetch.py -v` → FAIL (cannot import fetch_division).

- [ ] **Step 3: Write minimal implementation** — add to `src/ysr/scrapers/ecnl.py` (top: add the import and base URL; bottom: the function). Use the exact URL pattern confirmed in the Task 1 field map — the pattern below is representative:
```python
from ysr.scrapers.http import HttpClient

# Confirmed by Task 1 field map. Representative TGS public schedule endpoint:
_TGS_BASE = "https://public.totalglobalsports.com/api/Event"


def fetch_division(client: HttpClient, *, event_id: int, division_id: int) -> dict[str, Any]:
    url = f"{_TGS_BASE}/get-event-schedule/{event_id}/{division_id}"
    return client.get_json(url)
```
(Place the `from ysr.scrapers.http import HttpClient` import with the other imports at the top of the file. If the Task 1 field map shows a different URL shape, use that shape but keep `event_id` and `division_id` interpolated so the test's URL assertion holds.)

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_fetch.py -v` → PASS. Then `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add src/ysr/scrapers/ecnl.py tests/test_ecnl_fetch.py
git commit -m "feat: fetch TGS division schedule over http"
```

---

### Task 6: Ingest — resolve teams (scoped) and upsert games idempotently

**Files:**
- Create: `src/ysr/ingest.py`
- Create: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ingest.py`:
```python
import datetime as dt

from ysr.db import create_all, make_engine, make_session_factory
from ysr.ingest import IngestResult, get_or_create_source, ingest_games
from ysr.models import Game, Team
from ysr.scrapers.base import ScrapedGame
from sqlalchemy import func, select


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    return make_session_factory(engine)()


def _game(home: str, away: str, hs: int, aws: int, day: int) -> ScrapedGame:
    return ScrapedGame(
        date=dt.date(2026, 3, day),
        home_team=home,
        away_team=away,
        home_score=hs,
        away_score=aws,
        competition="ECNL Boys U16",
        raw={"home": home, "away": away},
    )


def test_ingest_creates_teams_and_games() -> None:
    with _session() as s:
        src = get_or_create_source(s, "ECNL", "https://x", "ysr.scrapers.ecnl")
        games = [_game("Strikers FC 2010 Boys", "Surf SC 2010 Boys", 3, 1, 2)]
        result = ingest_games(s, src.id, games, age_group="U16", gender="M")
        s.commit()

        assert result == IngestResult(inserted=1, updated=0, unchanged=0, teams_created=2)
        assert s.scalar(select(func.count()).select_from(Team)) == 2
        assert s.scalar(select(func.count()).select_from(Game)) == 1


def test_ingest_is_idempotent_and_updates_changed_scores() -> None:
    with _session() as s:
        src = get_or_create_source(s, "ECNL", "https://x", "ysr.scrapers.ecnl")
        ingest_games(s, src.id, [_game("A FC 2010 Boys", "B SC 2010 Boys", 1, 0, 2)], age_group="U16", gender="M")
        s.commit()

        # Re-run identical -> no new rows, no team duplication.
        r2 = ingest_games(s, src.id, [_game("A FC 2010 Boys", "B SC 2010 Boys", 1, 0, 2)], age_group="U16", gender="M")
        s.commit()
        assert r2 == IngestResult(inserted=0, updated=0, unchanged=1, teams_created=0)
        assert s.scalar(select(func.count()).select_from(Game)) == 1
        assert s.scalar(select(func.count()).select_from(Team)) == 2

        # Same fixture/date but a corrected score -> update in place.
        r3 = ingest_games(s, src.id, [_game("A FC 2010 Boys", "B SC 2010 Boys", 2, 2, 2)], age_group="U16", gender="M")
        s.commit()
        assert r3 == IngestResult(inserted=0, updated=1, unchanged=0, teams_created=0)
        g = s.scalar(select(Game))
        assert g is not None and g.home_score == 2 and g.away_score == 2


def test_ingest_does_not_conflate_different_age_groups() -> None:
    with _session() as s:
        src = get_or_create_source(s, "ECNL", "https://x", "ysr.scrapers.ecnl")
        ingest_games(s, src.id, [_game("Strikers FC 2010 Boys", "Surf SC 2010 Boys", 3, 1, 2)], age_group="U16", gender="M")
        s.commit()
        # Same club names, different age group -> must create NEW teams, not reuse U16 ones.
        r = ingest_games(s, src.id, [_game("Strikers FC 2012 Boys", "Surf SC 2012 Boys", 0, 0, 2)], age_group="U14", gender="M")
        s.commit()
        assert r.teams_created == 2
        assert s.scalar(select(func.count()).select_from(Team)) == 4
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ingest.py -v` → FAIL (ModuleNotFoundError: ysr.ingest).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/ingest.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ysr.identity import Candidate, best_match
from ysr.models import Game, Source, Team, TeamAlias
from ysr.scrapers.base import ScrapedGame


@dataclass(frozen=True)
class IngestResult:
    inserted: int
    updated: int
    unchanged: int
    teams_created: int


def get_or_create_source(
    session: Session, name: str, base_url: str, scraper_module: str
) -> Source:
    existing = session.scalar(select(Source).where(Source.name == name))
    if existing is not None:
        return existing
    source = Source(name=name, base_url=base_url, scraper_module=scraper_module)
    session.add(source)
    session.flush()
    return source


def _resolve_team(
    session: Session, source_id: int, name: str, age_group: str, gender: str
) -> tuple[Team, bool]:
    rows = session.execute(
        select(TeamAlias.team_id, TeamAlias.alias_name)
        .join(Team, Team.id == TeamAlias.team_id)
        .where(
            TeamAlias.source_id == source_id,
            Team.age_group == age_group,
            Team.gender == gender,
        )
    ).all()
    candidates = [Candidate(team_id=r.team_id, name=r.alias_name) for r in rows]
    match = best_match(name, candidates)
    if match.team_id is not None:
        team = session.get(Team, match.team_id)
        assert team is not None
        return team, False

    team = Team(display_name=name, age_group=age_group, gender=gender)
    session.add(team)
    session.flush()
    session.add(TeamAlias(alias_name=name, source_id=source_id, team_id=team.id))
    session.flush()
    return team, True


def _upsert_game(
    session: Session, source_id: int, game: ScrapedGame, home_id: int, away_id: int
) -> str:
    existing = session.scalar(
        select(Game).where(
            Game.source_id == source_id,
            Game.date == game.date,
            Game.home_team_id == home_id,
            Game.away_team_id == away_id,
        )
    )
    if existing is None:
        session.add(
            Game(
                source_id=source_id,
                date=game.date,
                home_team_id=home_id,
                away_team_id=away_id,
                home_score=game.home_score,
                away_score=game.away_score,
                competition=game.competition,
                raw_payload=game.raw,
            )
        )
        return "inserted"
    if existing.home_score != game.home_score or existing.away_score != game.away_score:
        existing.home_score = game.home_score
        existing.away_score = game.away_score
        existing.raw_payload = game.raw
        return "updated"
    return "unchanged"


def ingest_games(
    session: Session,
    source_id: int,
    games: list[ScrapedGame],
    *,
    age_group: str,
    gender: str,
) -> IngestResult:
    inserted = updated = unchanged = teams_created = 0
    for game in games:
        home, home_new = _resolve_team(session, source_id, game.home_team, age_group, gender)
        away, away_new = _resolve_team(session, source_id, game.away_team, age_group, gender)
        teams_created += int(home_new) + int(away_new)
        outcome = _upsert_game(session, source_id, game, home.id, away.id)
        if outcome == "inserted":
            inserted += 1
        elif outcome == "updated":
            updated += 1
        else:
            unchanged += 1
        session.flush()
    return IngestResult(inserted=inserted, updated=updated, unchanged=unchanged, teams_created=teams_created)
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ingest.py -v` → PASS (3 tests). Then `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add src/ysr/ingest.py tests/test_ingest.py
git commit -m "feat: ingest scraped games with scoped identity and idempotent upsert"
```

---

### Task 7: CLI command and console-script entry

**Files:**
- Create: `src/ysr/cli.py`
- Modify: `pyproject.toml` (add `[project.scripts]`)
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** — `tests/test_cli.py` (patches `fetch_division` so no network; points the DB at a temp sqlite file via `DATABASE_URL`):
```python
import json
import pathlib

import pytest

from ysr.cli import main
from ysr.db import make_engine, make_session_factory
from ysr.models import Game
from sqlalchemy import func, select

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def test_main_ingests_division(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    payload = json.loads(FIXTURE.read_text())
    monkeypatch.setattr("ysr.cli.fetch_division", lambda *a, **k: payload)

    rc = main(["ecnl", "--event", "2040", "--division", "11501", "--age-group", "U16", "--gender", "M"])
    assert rc == 0

    session = make_session_factory(make_engine(db_url))()
    with session as s:
        assert s.scalar(select(func.count()).select_from(Game)) >= 1
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -v` → FAIL (ModuleNotFoundError: ysr.cli).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/cli.py`:
```python
from __future__ import annotations

import argparse

from ysr.db import create_all, make_engine, make_session_factory
from ysr.ingest import get_or_create_source, ingest_games
from ysr.scrapers.ecnl import fetch_division, parse_division
from ysr.scrapers.http import HttpClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ysr-scrape")
    sub = parser.add_subparsers(dest="source", required=True)
    ecnl = sub.add_parser("ecnl", help="Ingest one ECNL division from TGS")
    ecnl.add_argument("--event", type=int, required=True)
    ecnl.add_argument("--division", type=int, required=True)
    ecnl.add_argument("--age-group", required=True)
    ecnl.add_argument("--gender", required=True, choices=["M", "F"])
    args = parser.parse_args(argv)

    engine = make_engine()
    create_all(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        source = get_or_create_source(
            session, "ECNL", "https://www.totalglobalsports.com/ecnl/", "ysr.scrapers.ecnl"
        )
        payload = fetch_division(HttpClient(), event_id=args.event, division_id=args.division)
        games = parse_division(payload)
        result = ingest_games(
            session, source.id, games, age_group=args.age_group, gender=args.gender
        )
        session.commit()

    print(
        f"ingested: {result.inserted} new, {result.updated} updated, "
        f"{result.unchanged} unchanged, {result.teams_created} teams created"
    )
    return 0
```
Then add to `pyproject.toml` (a new top-level table):
```toml
[project.scripts]
ysr-scrape = "ysr.cli:main"
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -v` → PASS. Then `uv run pytest -q` (full suite green) and `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add src/ysr/cli.py pyproject.toml uv.lock tests/test_cli.py
git commit -m "feat: add ysr-scrape cli for ecnl ingestion"
```

---

### Task 8: Live end-to-end verification (manual, run once)

**Goal:** Confirm the scraper works against the real TGS API for the division captured in Task 1.

**Files:**
- Modify: `docs/superpowers/notes/ecnl-tgs-fieldmap.md` (append the verified run output)

- [ ] **Step 1: Create a local DB and run against the real division.** Use the real `--event`/`--division`/`--age-group`/`--gender` from Task 1:
```bash
export PATH="$HOME/.local/bin:$PATH"
DATABASE_URL="sqlite+pysqlite:///./live_check.db" uv run alembic upgrade head
DATABASE_URL="sqlite+pysqlite:///./live_check.db" uv run ysr-scrape ecnl --event <REAL_EVENT> --division <REAL_DIVISION> --age-group <REAL_AGE> --gender <M|F>
```
Expected: a line like `ingested: N new, 0 updated, 0 unchanged, M teams created` with N ≥ 1.

- [ ] **Step 2: Verify idempotency on real data.** Run the exact same command again.
Expected: `ingested: 0 new, ... unchanged, 0 teams created` (no duplicates; only updates if scores changed since the first run).

- [ ] **Step 3: Spot-check the data.**
```bash
DATABASE_URL="sqlite+pysqlite:///./live_check.db" uv run python -c "from ysr.db import make_engine, make_session_factory; from ysr.models import Game, Team; from sqlalchemy import select; s=make_session_factory(make_engine())(); print('teams', len(s.scalars(select(Team)).all())); g=s.scalar(select(Game)); print('sample', g.home_team_id, g.home_score, '-', g.away_score, g.away_team_id, g.date)"
```
Expected: non-zero team count and a sensible sample game.

- [ ] **Step 4: Record the result and clean up.** Append the actual command + output to `docs/superpowers/notes/ecnl-tgs-fieldmap.md`, then `rm -f live_check.db`.

- [ ] **Step 5: Commit.**
```bash
git add docs/superpowers/notes/ecnl-tgs-fieldmap.md
git commit -m "docs: record verified live ECNL ingestion run"
```

**If the live run fails** because TGS hard-blocks the `httpx` request (e.g. 403 even with headers): this triggers the spec's Playwright fallback. Stop and report — the fallback is a follow-up (replace `HttpClient.get_json` usage in `fetch_division` with a Playwright-rendered fetch that returns the same JSON); parse/ingest/CLI are unchanged.

---

## Self-Review

**Spec coverage:**
- §3 TGS source + spike → Task 1. §4 fetch strategy (httpx primary, Playwright fallback) → Tasks 4–5 + Task 8 fallback note. §5 components: `base.py`→T2, `http.py`→T4, `ecnl.py` fetch/parse→T3/T5, `ingest.py`→T6, `cli.py`+console script→T7. §6 completed-only→T3; scoped identity→T6 (`_resolve_team` filters by age_group/gender); idempotent upsert→T6; get-or-create source→T6; config not hardcoded→T7 CLI args. §8 testing (parser fixture, ingest dedup/scoping, live check)→T3/T6/T8. §10 success criteria→T7+T8.
- Gap check: `ScrapedTeam` from the spec's §5 was intentionally dropped (YAGNI — teams are derived from game names + division args; documented here so it's not a silent omission).

**Placeholder scan:** No TBD/TODO. Representative TGS field/URL names are explicitly flagged as spike-confirmed in Task 1, Task 3, and Task 5, with instructions to reconcile — not placeholders but documented variability isolated to two functions + one fixture.

**Type consistency:** `ScrapedGame(date, home_team, away_team, home_score, away_score, competition, raw)` defined in T2, used identically in T3/T5/T6/T7. `HttpClient(client=, min_interval=)` + `get_json(url, retries=)` defined T4, used T5/T7. `fetch_division(client, *, event_id, division_id)` defined T5, used T7 and patched in T7 test. `parse_division(payload) -> list[ScrapedGame]` defined T3, used T5/T7. `IngestResult(inserted, updated, unchanged, teams_created)`, `get_or_create_source(session, name, base_url, scraper_module)`, `ingest_games(session, source_id, games, *, age_group, gender)` defined T6, used identically in T6 tests and T7. Game fields (`raw_payload`, `home_team_id`, etc.) match Plan 1's models.
