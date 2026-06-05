# ECNL Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest one ECNL flight's teams and completed games from the TGS/AthleteOne JSON API into the Postgres data layer, idempotently, via a runnable `ysr-scrape` CLI command.

**Architecture:** A normalized record (`ScrapedGame`) flows `fetch (AthleteOne JSON via httpx) → parse (pure) → ingest (exact source-id team resolution + idempotent game upsert)`. Fetch (I/O) is isolated from parse (pure) so parsing is unit-tested against a committed fixture with no network.

**Tech Stack:** Python 3.12, httpx, SQLAlchemy 2.0 (existing), pytest, argparse. Tooling: ruff, black, mypy --strict.

**Depends on:** Plan 1 (Foundation & Data Layer). On branch `feat/ecnl-scraper` (already created off `feat/foundation-data-layer`).

**Spike confirmed (Task 1, done — see `docs/superpowers/notes/ecnl-tgs-fieldmap.md`):**
- API base `https://api.athleteone.com/api/Event`; reachable with browser-like headers via **httpx (no Playwright needed)**; responses are `{"result":"success","data":...}`.
- Games endpoint: `GET /get-schedules-by-flight/{eventID}/{flightID}/0` (teamID=0 = all teams).
- Game fields: `homeTeam`/`awayTeam` (names), `hometeamID`/`awayteamID` (**stable per-source team ids**), `homeTeamClub`/`awayTeamClub` (clubs), `hometeamscore`/`awayteamscore` (int or **null when unplayed**), `gameDate` (ISO), `flight` (competition name).
- **Identity keys on the stable TGS team id** (exact match), not fuzzy name matching — this avoids conflating a club's sibling teams ("... Boys Pink" vs "Blue"). Plan 1's fuzzy `ysr.identity` is retained for future sources lacking stable ids; it is **not used** by the ECNL scraper.

---

### Task 1: Discovery spike — DONE

Completed during planning. Captured `tests/fixtures/ecnl_event_sample.json` (real
`get-schedules-by-flight/3210/26840/0` response, 3 records: 2 played + 1 unplayed) and
`docs/superpowers/notes/ecnl-tgs-fieldmap.md` (endpoints + field map). Committed as
`spike: capture real ECNL/TGS schedule fixture and field map`. No action needed.

---

### Task 2: Add httpx dependency and the normalized records

**Files:**
- Modify: `pyproject.toml` (add `httpx` to `dependencies`)
- Create: `src/ysr/scrapers/__init__.py`
- Create: `src/ysr/scrapers/base.py`
- Create: `tests/test_scraped_game.py`

- [ ] **Step 1: Write the failing test** — `tests/test_scraped_game.py`:
```python
import dataclasses
import datetime as dt

from ysr.scrapers.base import ScrapedGame


def test_scraped_game_holds_fields_and_is_frozen() -> None:
    g = ScrapedGame(
        date=dt.date(2024, 8, 18),
        home_source_id="69758",
        home_team="Pittsburgh Riverhounds - Pre ECNL B13",
        home_club="Pittsburgh Riverhounds",
        away_source_id="93515",
        away_team="Manta United Soccer Club - Manta 2013 Boys Pink",
        away_club="Manta United Soccer Club",
        home_score=2,
        away_score=2,
        competition="U12 (2013) Pre-ECNL North - 9v9",
        raw={"matchID": 675970},
    )
    assert g.home_source_id == "69758"
    assert g.away_club == "Manta United Soccer Club"
    assert g.home_score == 2
    assert dataclasses.is_dataclass(g)
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_scraped_game.py -v` → FAIL (ModuleNotFoundError: ysr.scrapers.base).

- [ ] **Step 3: Add httpx + create the module.** Add `"httpx>=0.27"` to the `dependencies` array in `pyproject.toml` (keep existing entries). Create `src/ysr/scrapers/__init__.py` (empty). Create `src/ysr/scrapers/base.py`:
```python
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScrapedGame:
    date: dt.date
    home_source_id: str
    home_team: str
    home_club: str | None
    away_source_id: str
    away_team: str
    away_club: str | None
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

### Task 3: Parser — AthleteOne JSON → list[ScrapedGame]

**Files:**
- Create: `src/ysr/scrapers/ecnl.py`
- Create: `tests/test_ecnl_parse.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ecnl_parse.py` (loads the committed real fixture; only completed games returned; stable ids + clubs mapped):
```python
import datetime as dt
import json
import pathlib

from ysr.scrapers.ecnl import parse_division

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def test_parse_division_maps_completed_games_only() -> None:
    payload = json.loads(FIXTURE.read_text())
    games = parse_division(payload)

    # Fixture has 3 records: 2 played, 1 unplayed (null scores) -> only the 2 played parse.
    assert len(games) == 2
    for g in games:
        assert isinstance(g.date, dt.date)
        assert g.home_source_id and g.away_source_id
        assert g.home_team and g.away_team
        assert isinstance(g.home_score, int) and isinstance(g.away_score, int)
        assert g.raw

    g = games[0]
    assert g.home_source_id == "69758"
    assert g.home_club == "Pittsburgh Riverhounds"
    assert g.competition == "U12 (2013) Pre-ECNL North - 9v9"
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_parse.py -v` → FAIL (ModuleNotFoundError: ysr.scrapers.ecnl).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/scrapers/ecnl.py`:
```python
from __future__ import annotations

import datetime as dt
from typing import Any

from ysr.scrapers.base import ScrapedGame


def _parse_date(value: str) -> dt.date:
    return dt.datetime.fromisoformat(value).date()


def parse_division(payload: dict[str, Any]) -> list[ScrapedGame]:
    games: list[ScrapedGame] = []
    for match in payload["data"]:
        home_score = match.get("hometeamscore")
        away_score = match.get("awayteamscore")
        if home_score is None or away_score is None:
            continue  # unplayed — skip
        games.append(
            ScrapedGame(
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
        )
    return games
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_parse.py -v` → PASS. Then `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add src/ysr/scrapers/ecnl.py tests/test_ecnl_parse.py
git commit -m "feat: parse AthleteOne flight payload into ScrapedGame list"
```

---

### Task 4: HTTP client — httpx with headers, rate-limit, retry

**Files:**
- Create: `src/ysr/scrapers/http.py`
- Create: `tests/test_http_client.py`

- [ ] **Step 1: Write the failing test** — `tests/test_http_client.py` (httpx MockTransport; monkeypatch sleep so retry is instant):
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

### Task 5: fetch_division — call the AthleteOne games endpoint

**Files:**
- Modify: `src/ysr/scrapers/ecnl.py` (add `fetch_division` + base URL + HttpClient import)
- Create: `tests/test_ecnl_fetch.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ecnl_fetch.py` (MockTransport returns the committed fixture; asserts the URL carries event+flight and downstream parse works):
```python
import json
import pathlib

import httpx

from ysr.scrapers.ecnl import fetch_division, parse_division
from ysr.scrapers.http import HttpClient

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def test_fetch_division_calls_endpoint_and_returns_payload() -> None:
    body = json.loads(FIXTURE.read_text())
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json=body)

    client = HttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval=0.0)
    payload = fetch_division(client, event_id=3210, flight_id=26840)

    assert "get-schedules-by-flight/3210/26840/0" in captured["url"]
    assert len(parse_division(payload)) == 2
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_fetch.py -v` → FAIL (cannot import fetch_division).

- [ ] **Step 3: Write minimal implementation** — add to `src/ysr/scrapers/ecnl.py`. Add the import at the top with the others, then add the base URL constant and function:
```python
from ysr.scrapers.http import HttpClient

_BASE = "https://api.athleteone.com/api/Event"


def fetch_division(client: HttpClient, *, event_id: int, flight_id: int) -> dict[str, Any]:
    # teamID=0 returns every game in the flight (confirmed by the Task 1 spike).
    url = f"{_BASE}/get-schedules-by-flight/{event_id}/{flight_id}/0"
    return client.get_json(url)
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ecnl_fetch.py -v` → PASS. Then `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add src/ysr/scrapers/ecnl.py tests/test_ecnl_fetch.py
git commit -m "feat: fetch AthleteOne flight schedule over http"
```

---

### Task 6: Ingest — resolve teams by stable source id and upsert games idempotently

**Files:**
- Create: `src/ysr/ingest.py`
- Create: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ingest.py`:
```python
import datetime as dt

from sqlalchemy import func, select

from ysr.db import create_all, make_engine, make_session_factory
from ysr.ingest import IngestResult, get_or_create_source, ingest_games
from ysr.models import Game, Team
from ysr.scrapers.base import ScrapedGame


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    return make_session_factory(engine)()


def _game(home_id: str, away_id: str, hs: int, aws: int, day: int = 2) -> ScrapedGame:
    return ScrapedGame(
        date=dt.date(2026, 3, day),
        home_source_id=home_id,
        home_team=f"Club {home_id} Team",
        home_club=f"Club {home_id}",
        away_source_id=away_id,
        away_team=f"Club {away_id} Team",
        away_club=f"Club {away_id}",
        home_score=hs,
        away_score=aws,
        competition="U16 Boys",
        raw={"home": home_id, "away": away_id},
    )


def test_ingest_creates_teams_and_games() -> None:
    with _session() as s:
        src = get_or_create_source(s, "ECNL", "https://x", "ysr.scrapers.ecnl")
        result = ingest_games(s, src.id, [_game("100", "200", 3, 1)], age_group="U16", gender="M")
        s.commit()

        assert result == IngestResult(inserted=1, updated=0, unchanged=0, teams_created=2)
        assert s.scalar(select(func.count()).select_from(Team)) == 2
        team = s.scalar(select(Team).where(Team.display_name == "Club 100 Team"))
        assert team is not None and team.club == "Club 100"


def test_ingest_is_idempotent_and_updates_changed_scores() -> None:
    with _session() as s:
        src = get_or_create_source(s, "ECNL", "https://x", "ysr.scrapers.ecnl")
        ingest_games(s, src.id, [_game("100", "200", 1, 0)], age_group="U16", gender="M")
        s.commit()

        r2 = ingest_games(s, src.id, [_game("100", "200", 1, 0)], age_group="U16", gender="M")
        s.commit()
        assert r2 == IngestResult(inserted=0, updated=0, unchanged=1, teams_created=0)
        assert s.scalar(select(func.count()).select_from(Game)) == 1
        assert s.scalar(select(func.count()).select_from(Team)) == 2

        r3 = ingest_games(s, src.id, [_game("100", "200", 2, 2)], age_group="U16", gender="M")
        s.commit()
        assert r3 == IngestResult(inserted=0, updated=1, unchanged=0, teams_created=0)
        g = s.scalar(select(Game))
        assert g is not None and g.home_score == 2 and g.away_score == 2


def test_sibling_teams_with_distinct_source_ids_are_not_conflated() -> None:
    with _session() as s:
        src = get_or_create_source(s, "ECNL", "https://x", "ysr.scrapers.ecnl")
        # Two same-club sibling teams (Pink=300, Blue=301) with near-identical names but distinct ids.
        g = ScrapedGame(
            date=dt.date(2026, 3, 2),
            home_source_id="300", home_team="Manta 2013 Boys Pink", home_club="Manta",
            away_source_id="301", away_team="Manta 2013 Boys Blue", away_club="Manta",
            home_score=1, away_score=0, competition="U13 Boys", raw={},
        )
        r = ingest_games(s, src.id, [g], age_group="U13", gender="M")
        s.commit()
        assert r.teams_created == 2
        assert s.scalar(select(func.count()).select_from(Team)) == 2
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ingest.py -v` → FAIL (ModuleNotFoundError: ysr.ingest).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/ingest.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    session: Session,
    source_id: int,
    source_team_id: str,
    name: str,
    club: str | None,
    age_group: str,
    gender: str,
) -> tuple[Team, bool]:
    # Exact match on the source's stable team id (stored as the alias).
    alias = session.scalar(
        select(TeamAlias).where(
            TeamAlias.source_id == source_id,
            TeamAlias.alias_name == source_team_id,
        )
    )
    if alias is not None:
        team = session.get(Team, alias.team_id)
        assert team is not None
        return team, False

    team = Team(display_name=name, club=club, age_group=age_group, gender=gender)
    session.add(team)
    session.flush()
    session.add(TeamAlias(alias_name=source_team_id, source_id=source_id, team_id=team.id))
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
        home, home_new = _resolve_team(
            session, source_id, game.home_source_id, game.home_team, game.home_club, age_group, gender
        )
        away, away_new = _resolve_team(
            session, source_id, game.away_source_id, game.away_team, game.away_club, age_group, gender
        )
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
git commit -m "feat: ingest games with stable-id team resolution and idempotent upsert"
```

---

### Task 7: CLI command and console-script entry

**Files:**
- Create: `src/ysr/cli.py`
- Modify: `pyproject.toml` (add `[project.scripts]`)
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** — `tests/test_cli.py` (patches `fetch_division` so no network; temp sqlite via `DATABASE_URL`):
```python
import json
import pathlib

import pytest
from sqlalchemy import func, select

from ysr.cli import main
from ysr.db import make_engine, make_session_factory
from ysr.models import Game

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def test_main_ingests_flight(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    payload = json.loads(FIXTURE.read_text())
    monkeypatch.setattr("ysr.cli.fetch_division", lambda *a, **k: payload)

    rc = main(["ecnl", "--event", "3210", "--flight", "26840", "--age-group", "U12", "--gender", "M"])
    assert rc == 0

    with make_session_factory(make_engine(db_url))() as s:
        assert s.scalar(select(func.count()).select_from(Game)) == 2
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
    ecnl = sub.add_parser("ecnl", help="Ingest one ECNL flight from AthleteOne/TGS")
    ecnl.add_argument("--event", type=int, required=True)
    ecnl.add_argument("--flight", type=int, required=True)
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
        payload = fetch_division(HttpClient(), event_id=args.event, flight_id=args.flight)
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
Then add to `pyproject.toml` (new top-level table):
```toml
[project.scripts]
ysr-scrape = "ysr.cli:main"
```

- [ ] **Step 4: Run test to verify it passes** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_cli.py -v` → PASS. Then `uv run pytest -q` (full suite green) and `uv run mypy src tests` → Success.

- [ ] **Step 5: Commit.**
```bash
git add src/ysr/cli.py pyproject.toml uv.lock tests/test_cli.py
git commit -m "feat: add ysr-scrape cli for ecnl flight ingestion"
```

---

### Task 8: Live end-to-end verification (manual, run once)

**Goal:** Confirm the scraper works against the real AthleteOne API. Use the spike's
known-good flight: event 3210, flight 26840 (U12 2013 Pre-ECNL North).

**Files:**
- Modify: `docs/superpowers/notes/ecnl-tgs-fieldmap.md` (append the verified run output)

- [ ] **Step 1: Create a local DB and run against the real flight.**
```bash
export PATH="$HOME/.local/bin:$PATH"
DATABASE_URL="sqlite+pysqlite:///./live_check.db" uv run alembic upgrade head
DATABASE_URL="sqlite+pysqlite:///./live_check.db" uv run ysr-scrape ecnl --event 3210 --flight 26840 --age-group U12 --gender M
```
Expected: `ingested: N new, 0 updated, 0 unchanged, M teams created` with N around 36 and M > 0.

- [ ] **Step 2: Verify idempotency on real data.** Run the exact same `ysr-scrape` command again.
Expected: `ingested: 0 new, 0 updated, <N> unchanged, 0 teams created` (no duplicates).

- [ ] **Step 3: Spot-check.**
```bash
DATABASE_URL="sqlite+pysqlite:///./live_check.db" uv run python -c "from ysr.db import make_engine, make_session_factory; from ysr.models import Game, Team; from sqlalchemy import select; s=make_session_factory(make_engine())(); print('teams', len(s.scalars(select(Team)).all())); g=s.scalar(select(Game)); print('sample', g.home_score, '-', g.away_score, g.date)"
```
Expected: non-zero team count and a sensible sample game.

- [ ] **Step 4: Record and clean up.** Append the actual commands + output to `docs/superpowers/notes/ecnl-tgs-fieldmap.md`, then `rm -f live_check.db`.

- [ ] **Step 5: Commit.**
```bash
git add docs/superpowers/notes/ecnl-tgs-fieldmap.md
git commit -m "docs: record verified live ECNL ingestion run"
```

---

## Self-Review

**Spec coverage:** TGS source + spike → Task 1 (done). httpx fetch (no Playwright) → Tasks 4–5. Components: `base.py`→T2, `http.py`→T4, `ecnl.py` parse/fetch→T3/T5, `ingest.py`→T6, `cli.py`+console script→T7. Completed-only→T3. Idempotent upsert + get-or-create source→T6. Config not hardcoded (event/flight/age/gender as CLI args)→T7. Testing (parser fixture, ingest dedup + sibling non-conflation, live check)→T3/T6/T8. **Deviation from the original spec, justified by the spike:** identity keys on the stable TGS team id (exact match) instead of fuzzy `ysr.identity` matching — recorded in the field-map note and the header above. `Team.club` is now populated (from `homeTeamClub`/`awayTeamClub`).

**Placeholder scan:** none — all field names/endpoints/params are spike-confirmed real values.

**Type consistency:** `ScrapedGame(date, home_source_id, home_team, home_club, away_source_id, away_team, away_club, home_score, away_score, competition, raw)` defined T2, used identically T3/T5/T6/T7. `HttpClient(client=, min_interval=)` + `get_json(url, retries=)` T4 → used T5/T7. `fetch_division(client, *, event_id, flight_id)` T5 → used T7 (patched in T7 test). `parse_division(payload)->list[ScrapedGame]` T3 → used T5/T7. `IngestResult(inserted, updated, unchanged, teams_created)`, `get_or_create_source(session, name, base_url, scraper_module)`, `ingest_games(session, source_id, games, *, age_group, gender)` T6 → used T6 tests + T7. Game/Team/TeamAlias fields match Plan 1 models.
