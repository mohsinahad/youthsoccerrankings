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
        assert s.scalar(select(func.count()).select_from(Game)) == 4
        assert s.scalar(select(func.count()).select_from(Team)) == 8
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
        assert s.scalar(select(func.count()).select_from(Game)) == 3


def test_errors_on_unmigrated_db(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'empty.db'}")
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        main(["ecnl", "--event", "3210"])
