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
        team = Team(display_name="Strikers FC", birth_year=2010, gender="M", state="CA")
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
        home = Team(display_name="Home", birth_year=2010, gender="M")
        away = Team(display_name="Away", birth_year=2010, gender="M")
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
                raw_payload={"source_row": 42},
            )
        )
        s.commit()

        game = s.scalar(select(Game))
        assert game is not None
        assert game.home_score == 3 and game.away_score == 1
        assert game.raw_payload == {"source_row": 42}
