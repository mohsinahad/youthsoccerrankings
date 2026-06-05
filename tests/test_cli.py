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
