import datetime as dt
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Game, Rating, Team
from ysr.web.app import app, get_session


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        a = Team(display_name="Alpha FC", club="Alpha", birth_year=2013, gender="M")
        b = Team(display_name="Beta FC", club="Beta", birth_year=2013, gender="M")
        s.add_all([a, b])
        s.flush()
        s.add(Game(source_id=1, date=dt.date(2026, 3, 1), home_team_id=a.id, away_team_id=b.id, home_score=3, away_score=0))
        now = dt.datetime(2026, 3, 2)
        s.add_all([
            Rating(team_id=a.id, rating=1700.0, rating_deviation=90.0, volatility=0.06, is_provisional=False, computed_at=now),
            Rating(team_id=b.id, rating=1400.0, rating_deviation=150.0, volatility=0.06, is_provisional=True, computed_at=now),
        ])
        s.commit()

    def _override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_index_lists_pools(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "2013" in resp.text


def test_rankings_orders_teams_and_marks_provisional(client: TestClient) -> None:
    resp = client.get("/rankings", params={"birth_year": 2013, "gender": "M"})
    assert resp.status_code == 200
    body = resp.text
    assert body.index("Alpha FC") < body.index("Beta FC")
    assert "provisional" in body.lower()


def test_rankings_defaults_to_first_pool_when_unfiltered(client: TestClient) -> None:
    resp = client.get("/rankings")
    assert resp.status_code == 200
    assert "Alpha FC" in resp.text


def test_team_page_shows_record_and_results(client: TestClient) -> None:
    resp = client.get("/teams/1")
    assert resp.status_code == 200
    body = resp.text
    assert "Alpha FC" in body
    assert "Beta FC" in body
    assert "3" in body and "0" in body


def test_team_page_unknown_returns_404(client: TestClient) -> None:
    resp = client.get("/teams/9999")
    assert resp.status_code == 404
