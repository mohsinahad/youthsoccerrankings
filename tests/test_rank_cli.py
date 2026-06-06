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
        a = Team(display_name="A", birth_year=2013, gender="M")
        b = Team(display_name="B", birth_year=2013, gender="M")
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
