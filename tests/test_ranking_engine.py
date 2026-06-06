import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Game, Rating, RatingHistory, Source, Team
from ysr.ranking.engine import RankingRunResult, recompute_all


def _session() -> Session:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    return make_session_factory(engine)()


def _seed_pool(s: Session) -> dict[str, int]:
    src = Source(name="ECNL", base_url="x", scraper_module="m")
    a = Team(display_name="A", birth_year=2013, gender="M")
    b = Team(display_name="B", birth_year=2013, gender="M")
    c = Team(display_name="C", birth_year=2013, gender="M")
    s.add_all([src, a, b, c])
    s.flush()
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
        assert ra.is_provisional is True
        assert ra.rating_deviation < 350.0


def test_recompute_is_idempotent_for_ratings_and_appends_history() -> None:
    with _session() as s:
        _seed_pool(s)
        recompute_all(s)
        s.commit()
        recompute_all(s)
        s.commit()
        assert s.scalar(select(func.count()).select_from(Rating)) == 3
        assert s.scalar(select(func.count()).select_from(RatingHistory)) == 6


def test_recompute_skips_pool_with_no_games() -> None:
    with _session() as s:
        s.add(Team(display_name="Lonely", birth_year=2016, gender="F"))
        s.commit()
        result = recompute_all(s)
        s.commit()
        assert result.teams_rated == 0
        assert s.scalar(select(func.count()).select_from(Rating)) == 0
