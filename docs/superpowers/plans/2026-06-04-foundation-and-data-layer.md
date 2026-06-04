# Foundation & Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tested Python data layer for Youth Soccer Rankings — project scaffolding, Postgres schema (teams, games, ratings, sources, aliases), and team identity resolution — so later subsystems (scrapers, ranking engine, web app) have a solid foundation to read and write.

**Architecture:** A single Python package `ysr` using SQLAlchemy 2.0 (typed ORM) for models, Alembic for migrations, and pure functions for team identity resolution (fuzzy name matching). Production runs on Replit's Postgres; tests run against in-memory SQLite via SQLAlchemy so they're fast and dependency-free. Pure logic (identity matching) is separated from I/O (DB session) per the project's functional-core / impure-edges preference.

**Tech Stack:** Python 3.12, `uv` (dependency management), SQLAlchemy 2.0, Alembic, `psycopg[binary]` (Postgres driver), `rapidfuzz` (fuzzy matching), `pydantic-settings` (config), `pytest`. Tooling: `ruff`, `black`, `mypy`.

This is **Plan 1 of 5** (see spec §3 phasing). It depends on nothing; later plans depend on it.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/ysr/__init__.py`
- Create: `tests/test_smoke.py`
- Create: `.gitignore`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_package_imports() -> None:
    import ysr

    assert ysr.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ysr'` (or pytest not installed yet).

- [ ] **Step 3: Create the project files**

`pyproject.toml`:
```toml
[project]
name = "ysr"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.1",
    "rapidfuzz>=3.6",
    "pydantic-settings>=2.2",
]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.4", "black>=24.0", "mypy>=1.10"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ysr"]

[tool.pytest.ini_options]
pythonpath = ["src"]

[tool.ruff]
line-length = 100

[tool.black]
line-length = 100

[tool.mypy]
strict = true
mypy_path = "src"
```

`src/ysr/__init__.py`:
```python
__version__ = "0.1.0"
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.db
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ysr/__init__.py tests/test_smoke.py .gitignore
git commit -m "feat: scaffold ysr python package"
```

---

### Task 2: Configuration module

**Files:**
- Create: `src/ysr/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from ysr.config import Settings


def test_default_database_url_is_sqlite_memory() -> None:
    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///:memory:"


def test_database_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host/db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ysr.config'`.

- [ ] **Step 3: Write minimal implementation**

`src/ysr/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+pysqlite:///:memory:"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/ysr/config.py tests/test_config.py
git commit -m "feat: add settings loaded from env"
```

---

### Task 3: ORM models

**Files:**
- Create: `src/ysr/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
import datetime as dt

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ysr.models import Base, Game, Source, Team, TeamAlias


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_create_team_with_alias() -> None:
    with _session() as s:
        source = Source(name="ECNL", base_url="https://theecnl.com", scraper_module="ysr.scrapers.ecnl")
        team = Team(display_name="Strikers FC", age_group="U15", gender="M", state="CA")
        s.add_all([source, team])
        s.flush()
        s.add(TeamAlias(alias_name="Strikers FC 2010B", source_id=source.id, team_id=team.id))
        s.commit()

        loaded = s.scalar(select(Team).where(Team.display_name == "Strikers FC"))
        assert loaded is not None
        assert loaded.aliases[0].alias_name == "Strikers FC 2010B"


def test_create_game_links_two_teams() -> None:
    with _session() as s:
        source = Source(name="ECNL", base_url="x", scraper_module="m")
        home = Team(display_name="Home", age_group="U15", gender="M")
        away = Team(display_name="Away", age_group="U15", gender="M")
        s.add_all([source, home, away])
        s.flush()
        s.add(
            Game(
                source_id=source.id,
                date=dt.date(2026, 3, 2),
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=3,
                away_score=1,
                competition="ECNL National",
            )
        )
        s.commit()

        game = s.scalar(select(Game))
        assert game is not None
        assert game.home_score == 3 and game.away_score == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ysr.models'`.

- [ ] **Step 3: Write minimal implementation**

`src/ysr/models.py`:
```python
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    base_url: Mapped[str] = mapped_column(String)
    scraper_module: Mapped[str] = mapped_column(String)
    last_run: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="idle")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String)
    club: Mapped[str | None] = mapped_column(String, nullable=True)
    age_group: Mapped[str] = mapped_column(String)
    gender: Mapped[str] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)

    aliases: Mapped[list[TeamAlias]] = relationship(back_populates="team")


class TeamAlias(Base):
    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("alias_name", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alias_name: Mapped[str] = mapped_column(String)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    team: Mapped[Team] = relationship(back_populates="aliases")


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("source_id", "date", "home_team_id", "away_team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    date: Mapped[dt.date] = mapped_column(Date)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    competition: Mapped[str | None] = mapped_column(String, nullable=True)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("team_id", "age_group", "gender"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    age_group: Mapped[str] = mapped_column(String)
    gender: Mapped[str] = mapped_column(String)
    rating: Mapped[float] = mapped_column(Float)
    rating_deviation: Mapped[float] = mapped_column(Float)
    volatility: Mapped[float] = mapped_column(Float)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime)


class RatingHistory(Base):
    __tablename__ = "rating_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    rating: Mapped[float] = mapped_column(Float)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/ysr/models.py tests/test_models.py
git commit -m "feat: add ORM models for sources, teams, games, ratings"
```

---

### Task 4: Database session factory

**Files:**
- Create: `src/ysr/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

`tests/test_db.py`:
```python
from sqlalchemy import select

from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Source


def test_session_factory_round_trip() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as s:
        s.add(Source(name="ECNL", base_url="x", scraper_module="m"))
        s.commit()

    with session_factory() as s:
        loaded = s.scalar(select(Source).where(Source.name == "ECNL"))
        assert loaded is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ysr.db'`.

- [ ] **Step 3: Write minimal implementation**

`src/ysr/db.py`:
```python
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ysr.config import get_settings
from ysr.models import Base


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url)


def create_all(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ysr/db.py tests/test_db.py
git commit -m "feat: add database engine and session factory"
```

---

### Task 5: Team identity resolution (pure functions)

This is the spec's first-class "same team named differently across sources" concern (spec §6). Pure logic, no DB — fully unit-testable.

**Files:**
- Create: `src/ysr/identity.py`
- Create: `tests/test_identity.py`

- [ ] **Step 1: Write the failing test**

`tests/test_identity.py`:
```python
from ysr.identity import Candidate, best_match, normalize_name


def test_normalize_lowercases_and_collapses_whitespace() -> None:
    assert normalize_name("  Strikers-FC   2010B ") == "strikers fc 2010b"


def test_best_match_returns_exact_candidate() -> None:
    candidates = [Candidate(team_id=1, name="Strikers FC"), Candidate(team_id=2, name="Surf SC")]
    result = best_match("strikers fc", candidates)
    assert result.team_id == 1
    assert result.score >= 99.0


def test_best_match_fuzzy_above_threshold() -> None:
    candidates = [Candidate(team_id=1, name="Strikers FC 2010 Boys")]
    result = best_match("Strikers FC 2010B", candidates, threshold=80.0)
    assert result.team_id == 1


def test_best_match_below_threshold_returns_none() -> None:
    candidates = [Candidate(team_id=1, name="Strikers FC")]
    result = best_match("Totally Different Club", candidates, threshold=85.0)
    assert result.team_id is None


def test_best_match_empty_candidates() -> None:
    result = best_match("anything", [])
    assert result.team_id is None
    assert result.score == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ysr.identity'`.

- [ ] **Step 3: Write minimal implementation**

`src/ysr/identity.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process


@dataclass(frozen=True)
class Candidate:
    team_id: int
    name: str


@dataclass(frozen=True)
class MatchResult:
    team_id: int | None
    score: float


def normalize_name(name: str) -> str:
    return " ".join(name.lower().replace("-", " ").split())


def best_match(
    query: str,
    candidates: list[Candidate],
    threshold: float = 85.0,
) -> MatchResult:
    if not candidates:
        return MatchResult(team_id=None, score=0.0)

    choices = {c.team_id: normalize_name(c.name) for c in candidates}
    match = process.extractOne(
        normalize_name(query),
        choices,
        scorer=fuzz.token_sort_ratio,
    )
    if match is None:
        return MatchResult(team_id=None, score=0.0)

    _value, score, key = match
    if score >= threshold:
        return MatchResult(team_id=key, score=score)
    return MatchResult(team_id=None, score=score)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_identity.py -v`
Expected: PASS (all five tests).

- [ ] **Step 5: Commit**

```bash
git add src/ysr/identity.py tests/test_identity.py
git commit -m "feat: add fuzzy team identity resolution"
```

---

### Task 6: Alembic migrations

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/` (initial migration generated into here)

- [ ] **Step 1: Initialize Alembic**

Run: `uv run alembic init alembic`
This generates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, and an empty `alembic/versions/`.

- [ ] **Step 2: Wire Alembic to our models and settings**

Replace the relevant parts of `alembic/env.py` so it imports our metadata and DB URL. Set `target_metadata` and override the URL:
```python
from ysr.config import get_settings
from ysr.models import Base

target_metadata = Base.metadata

# inside run_migrations_online(), before engine creation, ensure the URL comes from settings:
config.set_main_option("sqlalchemy.url", get_settings().database_url)
```
(Leave the rest of the generated `env.py` intact.)

- [ ] **Step 3: Generate the initial migration against a Postgres URL**

Set a local/Replit Postgres URL so autogenerate reflects Postgres types:
```bash
DATABASE_URL="postgresql+psycopg://localhost/ysr_dev" \
  uv run alembic revision --autogenerate -m "initial schema"
```
Expected: a new file in `alembic/versions/` containing `create_table` calls for `sources`, `teams`, `team_aliases`, `games`, `ratings`, `rating_history`.

- [ ] **Step 4: Verify the migration applies cleanly**

```bash
DATABASE_URL="postgresql+psycopg://localhost/ysr_dev" uv run alembic upgrade head
DATABASE_URL="postgresql+psycopg://localhost/ysr_dev" uv run alembic downgrade base
```
Expected: upgrade creates all six tables; downgrade drops them, both without error.

- [ ] **Step 5: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat: add alembic migrations with initial schema"
```

---

## Self-Review

**Spec coverage (§6 Data Model):** `sources`, `teams`, `team_aliases`, `games`, `ratings`, `rating_history` — all present in Task 3. Team identity resolution (§6) — Task 5. Replit Postgres target — Task 6 generates Postgres-typed migrations; SQLite used only for fast tests. Scraper/ranking/web subsystems are intentionally out of scope (later plans, see header).

**Placeholder scan:** No TBD/TODO; every code step contains complete code; every command has expected output.

**Type consistency:** `make_engine`/`create_all`/`make_session_factory` (Task 4) match their test usage (Task 4 test). `Candidate`/`MatchResult`/`best_match`/`normalize_name` (Task 5) match the test (Task 5). Model class/column names in Task 3 match references in Tasks 4 and 6. `database_url` setting name consistent across Tasks 2, 4, 6.

**Note for executor:** Tasks 1–5 are fully self-contained and run on SQLite with no external services. Task 6 requires a reachable Postgres instance (local for dev, or Replit's built-in DB) to autogenerate and verify the migration.
