import datetime as dt

from sqlalchemy.orm import Session

from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Game, Rating, RatingHistory, Team
from ysr.web.queries import list_pools, pool_rankings, team_detail


def _session() -> Session:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    return make_session_factory(engine)()


def _seed(s: Session) -> dict[str, int]:
    a = Team(display_name="A", club="A FC", age_group="U16", gender="M")
    b = Team(display_name="B", club="B FC", age_group="U16", gender="M")
    c = Team(display_name="C", club="C FC", age_group="U16", gender="M")
    s.add_all([a, b, c])
    s.flush()
    s.add_all([
        Game(source_id=1, date=dt.date(2026, 3, 1), home_team_id=a.id, away_team_id=b.id, home_score=1, away_score=0),
        Game(source_id=1, date=dt.date(2026, 3, 2), home_team_id=a.id, away_team_id=c.id, home_score=2, away_score=0),
        Game(source_id=1, date=dt.date(2026, 3, 3), home_team_id=b.id, away_team_id=c.id, home_score=1, away_score=0),
    ])
    now = dt.datetime(2026, 3, 4)
    s.add_all([
        Rating(team_id=a.id, rating=1700.0, rating_deviation=90.0, volatility=0.06, is_provisional=False, computed_at=now),
        Rating(team_id=b.id, rating=1500.0, rating_deviation=120.0, volatility=0.06, is_provisional=True, computed_at=now),
        Rating(team_id=c.id, rating=1300.0, rating_deviation=95.0, volatility=0.06, is_provisional=False, computed_at=now),
        RatingHistory(team_id=a.id, rating=1600.0, computed_at=dt.datetime(2026, 2, 25)),
        RatingHistory(team_id=a.id, rating=1700.0, computed_at=now),
    ])
    s.commit()
    return {"a": a.id, "b": b.id, "c": c.id}


def test_list_pools_counts_rated_teams() -> None:
    with _session() as s:
        _seed(s)
        pools = list_pools(s)
        assert len(pools) == 1
        assert pools[0].age_group == "U16" and pools[0].gender == "M"
        assert pools[0].team_count == 3


def test_pool_rankings_order_record_and_provisional() -> None:
    with _session() as s:
        ids = _seed(s)
        ranked = pool_rankings(s, "U16", "M")
        assert [r.team_id for r in ranked] == [ids["a"], ids["b"], ids["c"]]
        assert [r.rank for r in ranked] == [1, 2, 3]
        a = ranked[0]
        assert a.club == "A FC"
        assert (a.wins, a.draws, a.losses) == (2, 0, 0)
        assert a.is_provisional is False
        b = ranked[1]
        assert (b.wins, b.draws, b.losses) == (1, 0, 1)
        assert b.is_provisional is True


def test_team_detail_has_rank_history_and_results() -> None:
    with _session() as s:
        ids = _seed(s)
        d = team_detail(s, ids["a"])
        assert d is not None
        assert d.team.rank == 1
        assert d.age_group == "U16" and d.gender == "M"
        assert len(d.history) == 2
        assert [h.rating for h in d.history] == [1600.0, 1700.0]
        assert len(d.results) == 2
        assert all(r.outcome == "W" for r in d.results)
        assert d.results[0].date >= d.results[1].date


def test_team_detail_missing_returns_none() -> None:
    with _session() as s:
        _seed(s)
        assert team_detail(s, 9999) is None
