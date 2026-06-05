# Ranking Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute Glicko-2 ratings (rating + confidence + provisional flag) for every team per `(age_group, gender)` pool from completed games, runnable via a `ysr-rank` CLI.

**Architecture:** A pure, tested Glicko-2 core (`ranking/glicko2.py`); a normalized one-rating-per-team `Rating` model; an engine (`ranking/engine.py`) that recomputes all pools from scratch (single rating period) and upserts `Rating` + appends `RatingHistory`; a `ysr-rank` CLI.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Alembic, pytest, argparse, stdlib `math`. mypy --strict, ruff.

**Depends on:** Plans 1–3 (merged). On branch `feat/ranking-engine` (already created off `main`).

**Environment:** `uv` at `~/.local/bin/uv` (not on PATH). Prefix every uv command: `export PATH="$HOME/.local/bin:$PATH" && uv run ...`. Run `uv run ruff check .` as part of each task's verification (in addition to pytest + mypy).

---

### Task 1: Glicko-2 core (pure)

**Files:**
- Create: `src/ysr/ranking/__init__.py`
- Create: `src/ysr/ranking/glicko2.py`
- Create: `tests/test_glicko2.py`

- [ ] **Step 1: Write the failing test** — `tests/test_glicko2.py`:
```python
import math

from ysr.ranking.glicko2 import Glicko, rate


def test_rate_matches_glickman_paper_example() -> None:
    # Worked example from Glickman's Glicko-2 paper.
    player = Glicko(1500.0, 200.0, 0.06)
    results = [
        (Glicko(1400.0, 30.0), 1.0),
        (Glicko(1550.0, 100.0), 0.0),
        (Glicko(1700.0, 300.0), 0.0),
    ]
    new = rate(player, results)
    assert abs(new.rating - 1464.05) < 0.5
    assert abs(new.rd - 151.52) < 0.5
    assert abs(new.vol - 0.05999) < 1e-4


def test_rate_no_results_inflates_rd_only() -> None:
    player = Glicko(1500.0, 200.0, 0.06)
    new = rate(player, [])
    assert new.rating == 1500.0
    assert new.vol == 0.06
    expected_rd = 173.7178 * math.sqrt((200.0 / 173.7178) ** 2 + 0.06**2)
    assert abs(new.rd - expected_rd) < 1e-6


def test_rate_winner_ends_above_loser() -> None:
    a = rate(Glicko(), [(Glicko(), 1.0)])
    b = rate(Glicko(), [(Glicko(), 0.0)])
    assert a.rating > b.rating
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_glicko2.py -v` → FAIL (ModuleNotFoundError: ysr.ranking.glicko2).

- [ ] **Step 3: Write minimal implementation** — create `src/ysr/ranking/__init__.py` (empty) and `src/ysr/ranking/glicko2.py`:
```python
from __future__ import annotations

import math
from dataclasses import dataclass

_SCALE = 173.7178
_DEFAULT_RATING = 1500.0
_DEFAULT_RD = 350.0
_DEFAULT_VOL = 0.06
_EPSILON = 1e-6


@dataclass(frozen=True)
class Glicko:
    rating: float = _DEFAULT_RATING
    rd: float = _DEFAULT_RD
    vol: float = _DEFAULT_VOL


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi**2 / math.pi**2)


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def rate(player: Glicko, results: list[tuple[Glicko, float]], *, tau: float = 0.5) -> Glicko:
    mu = (player.rating - _DEFAULT_RATING) / _SCALE
    phi = player.rd / _SCALE
    sigma = player.vol

    if not results:
        phi_star = math.sqrt(phi**2 + sigma**2)
        return Glicko(rating=player.rating, rd=_SCALE * phi_star, vol=sigma)

    opponents = [((o.rating - _DEFAULT_RATING) / _SCALE, o.rd / _SCALE, s) for o, s in results]

    v_inv = 0.0
    delta_sum = 0.0
    for mu_j, phi_j, score in opponents:
        e = _expected(mu, mu_j, phi_j)
        v_inv += _g(phi_j) ** 2 * e * (1.0 - e)
        delta_sum += _g(phi_j) * (score - e)
    v = 1.0 / v_inv
    delta = v * delta_sum

    a = math.log(sigma**2)

    def f(x: float) -> float:
        ex = math.exp(x)
        numerator = ex * (delta**2 - phi**2 - v - ex)
        denominator = 2.0 * (phi**2 + v + ex) ** 2
        return numerator / denominator - (x - a) / tau**2

    big_a = a
    if delta**2 > phi**2 + v:
        big_b = math.log(delta**2 - phi**2 - v)
    else:
        k = 1
        while f(a - k * tau) < 0.0:
            k += 1
        big_b = a - k * tau

    f_a = f(big_a)
    f_b = f(big_b)
    while abs(big_b - big_a) > _EPSILON:
        c = big_a + (big_a - big_b) * f_a / (f_b - f_a)
        f_c = f(c)
        if f_c * f_b <= 0.0:
            big_a = big_b
            f_a = f_b
        else:
            f_a = f_a / 2.0
        big_b = c
        f_b = f_c

    sigma_prime = math.exp(big_a / 2.0)
    phi_star = math.sqrt(phi**2 + sigma_prime**2)
    phi_prime = 1.0 / math.sqrt(1.0 / phi_star**2 + 1.0 / v)
    mu_prime = mu + phi_prime**2 * delta_sum

    return Glicko(
        rating=_SCALE * mu_prime + _DEFAULT_RATING,
        rd=_SCALE * phi_prime,
        vol=sigma_prime,
    )
```

- [ ] **Step 4: Run tests to verify they pass** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_glicko2.py -v` → 3 PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run ruff check . && uv run mypy src tests` → clean.

- [ ] **Step 5: Commit**
```bash
git add src/ysr/ranking/__init__.py src/ysr/ranking/glicko2.py tests/test_glicko2.py
git commit -m "feat: add tested Glicko-2 rating core"
```

---

### Task 2: Normalize the `Rating` model + regenerate the migration

The project has no production database yet, so we regenerate the single initial migration (as was done for `raw_payload` in Plan 1) rather than writing an ALTER — this keeps the migration simple and dialect-agnostic.

**Files:**
- Modify: `src/ysr/models.py` (the `Rating` class)
- Replace: `alembic/versions/302a5be3fc1a_initial_schema.py` (delete + regenerate)

- [ ] **Step 1: Edit the `Rating` model** — in `src/ysr/models.py`, replace the entire `Rating` class with (drop `age_group`/`gender`, drop the old `__table_args__`, make `team_id` unique):
```python
class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), unique=True)
    rating: Mapped[float] = mapped_column(Float)
    rating_deviation: Mapped[float] = mapped_column(Float)
    volatility: Mapped[float] = mapped_column(Float)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime)
```
(Leave `UniqueConstraint` imported — it's still used by `TeamAlias` and `Game`. Leave `RatingHistory` unchanged.)

- [ ] **Step 2: Confirm nothing references the dropped fields** — run `grep -rn "Rating(" src tests` and `grep -rn "\.age_group\|\.gender" src tests`. Verify no code constructs `Rating` with `age_group`/`gender` or reads them off a `Rating` (only `Team.age_group`/`Team.gender` usages are fine). If any exist, STOP and report — there should be none.

- [ ] **Step 3: Regenerate the initial migration**
```bash
export PATH="$HOME/.local/bin:$PATH"
rm alembic/versions/302a5be3fc1a_initial_schema.py
DATABASE_URL="sqlite+pysqlite:///./_regen.db" uv run alembic revision --autogenerate -m "initial schema"
```
Open the new file in `alembic/versions/` and CONFIRM: the `ratings` `create_table` has columns `id, team_id, rating, rating_deviation, volatility, is_provisional, computed_at` (NO `age_group`/`gender`) and a unique constraint/index on `team_id`; all six tables are still present. If `ratings` still has `age_group`/`gender`, STOP and report.

- [ ] **Step 4: Verify the migration applies and reverses, then clean up**
```bash
export PATH="$HOME/.local/bin:$PATH"
DATABASE_URL="sqlite+pysqlite:///./_regen.db" uv run alembic upgrade head
DATABASE_URL="sqlite+pysqlite:///./_regen.db" uv run alembic downgrade base
rm -f _regen.db
uv run pytest -q && uv run ruff check . && uv run mypy src tests
```
Expected: upgrade/downgrade run clean; full suite green; ruff + mypy clean.

- [ ] **Step 5: Commit**
```bash
git add src/ysr/models.py alembic/versions/
git commit -m "feat: normalize Rating to one row per team (drop age_group/gender)"
```

---

### Task 3: Ranking engine

**Files:**
- Create: `src/ysr/ranking/engine.py`
- Create: `tests/test_ranking_engine.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ranking_engine.py`:
```python
import datetime as dt

from sqlalchemy import func, select

from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Game, Rating, RatingHistory, Source, Team
from ysr.ranking.engine import RankingRunResult, recompute_all


def _session():  # type: ignore[no-untyped-def]
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    return make_session_factory(engine)()


def _seed_pool(s) -> dict[str, int]:  # type: ignore[no-untyped-def]
    src = Source(name="ECNL", base_url="x", scraper_module="m")
    a = Team(display_name="A", age_group="U16", gender="M")
    b = Team(display_name="B", age_group="U16", gender="M")
    c = Team(display_name="C", age_group="U16", gender="M")
    s.add_all([src, a, b, c])
    s.flush()
    # A beats B and C; B beats C.
    s.add_all([
        Game(source_id=src.id, date=dt.date(2026, 3, 1), home_team_id=a.id, away_team_id=b.id, home_score=1, away_score=0),
        Game(source_id=src.id, date=dt.date(2026, 3, 2), home_team_id=a.id, away_team_id=c.id, home_score=1, away_score=0),
        Game(source_id=src.id, date=dt.date(2026, 3, 3), home_team_id=b.id, away_team_id=c.id, home_score=1, away_score=0),
    ])
    s.commit()
    return {"a": a.id, "b": b.id, "c": c.id}


def test_recompute_ranks_winner_highest_and_writes_history() -> None:
    with _session() as s:
        ids = _seed_pool(s)
        result = recompute_all(s)
        s.commit()

        assert isinstance(result, RankingRunResult)
        assert result.pools == 1
        assert result.teams_rated == 3
        assert s.scalar(select(func.count()).select_from(Rating)) == 3
        assert s.scalar(select(func.count()).select_from(RatingHistory)) == 3

        ra = s.scalar(select(Rating).where(Rating.team_id == ids["a"]))
        rb = s.scalar(select(Rating).where(Rating.team_id == ids["b"]))
        rc = s.scalar(select(Rating).where(Rating.team_id == ids["c"]))
        assert ra is not None and rb is not None and rc is not None
        assert ra.rating > rb.rating > rc.rating
        # Few games -> high RD -> provisional.
        assert ra.is_provisional is True
        assert ra.rating_deviation < 350.0  # RD shrank from default after games


def test_recompute_is_idempotent_for_ratings_and_appends_history() -> None:
    with _session() as s:
        _seed_pool(s)
        recompute_all(s)
        s.commit()
        recompute_all(s)
        s.commit()
        # One Rating row per team (upsert), but history appended each run.
        assert s.scalar(select(func.count()).select_from(Rating)) == 3
        assert s.scalar(select(func.count()).select_from(RatingHistory)) == 6


def test_recompute_skips_pool_with_no_games() -> None:
    with _session() as s:
        s.add(Team(display_name="Lonely", age_group="U10", gender="F"))
        s.commit()
        result = recompute_all(s)
        s.commit()
        assert result.teams_rated == 0
        assert s.scalar(select(func.count()).select_from(Rating)) == 0
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ranking_engine.py -v` → FAIL (ModuleNotFoundError: ysr.ranking.engine).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/ranking/engine.py`:
```python
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ysr.models import Game, Rating, RatingHistory, Team
from ysr.ranking.glicko2 import Glicko, rate

_PROVISIONAL_RD_THRESHOLD = 100.0


@dataclass(frozen=True)
class RankingRunResult:
    pools: int
    teams_rated: int
    history_rows: int


def _score(home_score: int, away_score: int, *, is_home: bool) -> float:
    mine, theirs = (home_score, away_score) if is_home else (away_score, home_score)
    if mine > theirs:
        return 1.0
    if mine < theirs:
        return 0.0
    return 0.5


def _upsert_rating(session: Session, team_id: int, g: Glicko, now: dt.datetime) -> None:
    is_provisional = g.rd > _PROVISIONAL_RD_THRESHOLD
    existing = session.scalar(select(Rating).where(Rating.team_id == team_id))
    if existing is None:
        session.add(
            Rating(
                team_id=team_id,
                rating=g.rating,
                rating_deviation=g.rd,
                volatility=g.vol,
                is_provisional=is_provisional,
                computed_at=now,
            )
        )
    else:
        existing.rating = g.rating
        existing.rating_deviation = g.rd
        existing.volatility = g.vol
        existing.is_provisional = is_provisional
        existing.computed_at = now


def recompute_all(session: Session) -> RankingRunResult:
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    pools = session.execute(select(Team.age_group, Team.gender).distinct()).tuples().all()

    pools_rated = 0
    teams_rated = 0
    history_rows = 0
    for age_group, gender in pools:
        team_ids = list(
            session.scalars(
                select(Team.id).where(Team.age_group == age_group, Team.gender == gender)
            ).all()
        )
        games = list(
            session.scalars(
                select(Game).where(
                    Game.home_team_id.in_(team_ids),
                    Game.away_team_id.in_(team_ids),
                )
            ).all()
        )
        if not games:
            continue

        results: dict[int, list[tuple[Glicko, float]]] = {}
        for game in games:
            results.setdefault(game.home_team_id, []).append(
                (Glicko(), _score(game.home_score, game.away_score, is_home=True))
            )
            results.setdefault(game.away_team_id, []).append(
                (Glicko(), _score(game.home_score, game.away_score, is_home=False))
            )

        pools_rated += 1
        for team_id, team_results in results.items():
            new = rate(Glicko(), team_results)
            _upsert_rating(session, team_id, new, now)
            session.add(RatingHistory(team_id=team_id, rating=new.rating, computed_at=now))
            teams_rated += 1
            history_rows += 1
        session.flush()

    return RankingRunResult(pools=pools_rated, teams_rated=teams_rated, history_rows=history_rows)
```

- [ ] **Step 4: Run tests to verify they pass** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_ranking_engine.py -v` → 3 PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy src tests` → all clean.

- [ ] **Step 5: Commit**
```bash
git add src/ysr/ranking/engine.py tests/test_ranking_engine.py
git commit -m "feat: ranking engine recomputes Glicko-2 ratings per pool"
```

---

### Task 4: `ysr-rank` CLI

**Files:**
- Create: `src/ysr/ranking/cli.py`
- Modify: `pyproject.toml` (`[project.scripts]`)
- Create: `tests/test_rank_cli.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_rank_cli.py`:
```python
import datetime as dt
import pathlib

import pytest
from sqlalchemy import func, select

from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Game, Rating, Source, Team
from ysr.ranking.cli import main


def _migrate_and_seed(db_url: str) -> None:
    engine = make_engine(db_url)
    create_all(engine)
    with make_session_factory(engine)() as s:
        src = Source(name="ECNL", base_url="x", scraper_module="m")
        a = Team(display_name="A", age_group="U16", gender="M")
        b = Team(display_name="B", age_group="U16", gender="M")
        s.add_all([src, a, b])
        s.flush()
        s.add(Game(source_id=src.id, date=dt.date(2026, 3, 1), home_team_id=a.id, away_team_id=b.id, home_score=2, away_score=0))
        s.commit()


def test_rank_cli_writes_ratings(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'rank.db'}"
    _migrate_and_seed(db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)

    rc = main([])
    assert rc == 0

    with make_session_factory(make_engine(db_url))() as s:
        assert s.scalar(select(func.count()).select_from(Rating)) == 2


def test_rank_cli_errors_on_unmigrated_db(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'empty.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        main([])
```

- [ ] **Step 2: Run test to verify it fails** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_rank_cli.py -v` → FAIL (ModuleNotFoundError: ysr.ranking.cli).

- [ ] **Step 3: Write minimal implementation** — `src/ysr/ranking/cli.py`:
```python
from __future__ import annotations

import argparse

from sqlalchemy import inspect

from ysr.db import make_engine, make_session_factory
from ysr.ranking.engine import recompute_all

_REQUIRED_TABLES = ("teams", "games", "ratings", "rating_history")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="ysr-rank", description="Recompute all team rankings"
    ).parse_args(argv)

    engine = make_engine()
    existing = set(inspect(engine).get_table_names())
    missing = [t for t in _REQUIRED_TABLES if t not in existing]
    if missing:
        raise RuntimeError(
            f"database not initialized (missing tables: {', '.join(missing)}); "
            "run `alembic upgrade head`"
        )

    with make_session_factory(engine)() as session:
        result = recompute_all(session)
        session.commit()

    print(
        f"ranked {result.teams_rated} teams across {result.pools} pools, "
        f"wrote {result.history_rows} history rows"
    )
    return 0
```
Then add the script entry to `pyproject.toml` under the existing `[project.scripts]` table (keep `ysr-scrape`):
```toml
[project.scripts]
ysr-scrape = "ysr.cli:main"
ysr-rank = "ysr.ranking.cli:main"
```

- [ ] **Step 4: Run tests to verify they pass** — `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/test_rank_cli.py -v` → 2 PASS. Then `export PATH="$HOME/.local/bin:$PATH" && uv run pytest -q && uv run ruff check . && uv run mypy src tests` → all clean. Confirm `export PATH="$HOME/.local/bin:$PATH" && uv run ysr-rank --help` prints usage.

- [ ] **Step 5: Commit**
```bash
git add src/ysr/ranking/cli.py pyproject.toml uv.lock tests/test_rank_cli.py
git commit -m "feat: add ysr-rank cli to recompute rankings"
```

---

## Self-Review

**Spec coverage:** §3 Glicko-2 core (Glicko + rate, no-results inflation, paper oracle) → Task 1. §4 single-period recompute → Task 3 (`recompute_all` uses default-Glicko opponents, one update per team). §5 `Rating` schema change + migration → Task 2. §6 engine (pools, scores, upsert, history, provisional via RD>100) → Task 3. §7 `ysr-rank` CLI + schema pre-check → Task 4. §9 testing (paper example, RD inflation, winner>loser, engine winner-highest/idempotent/empty-pool, CLI write + unmigrated error, migration up/down) → Tasks 1/2/3/4.

**Placeholder scan:** none — full algorithm code, full engine code, exact commands.

**Type consistency:** `Glicko(rating, rd, vol)` + `rate(player, results, *, tau=0.5) -> Glicko` (Task 1) used identically in Task 3. `RankingRunResult(pools, teams_rated, history_rows)` and `recompute_all(session) -> RankingRunResult` (Task 3) used in Task 3 tests and Task 4 CLI. New `Rating` columns (Task 2: team_id unique, rating, rating_deviation, volatility, is_provisional, computed_at) match exactly what `_upsert_rating` writes (Task 3) and what the engine/CLI tests query. `_REQUIRED_TABLES` names match the migration's tables. `.tuples()` keeps the pool query mypy-clean.

**Note on Task 2 migration:** regenerating the single initial migration is safe because no production DB exists yet (precedent: the `raw_payload` regeneration in Plan 1). It avoids SQLite ALTER/batch-mode complexity for the constraint change and stays dialect-agnostic.
