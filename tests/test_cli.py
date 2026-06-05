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
