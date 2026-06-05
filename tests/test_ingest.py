import datetime as dt

from sqlalchemy import func, select

from sqlalchemy.orm import Session

from ysr.db import create_all, make_engine, make_session_factory
from ysr.ingest import IngestResult, get_or_create_source, ingest_games
from ysr.models import Game, Team
from ysr.scrapers.base import ScrapedGame


def _session() -> Session:
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
