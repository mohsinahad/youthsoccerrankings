from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ysr.models import Game, Source, Team, TeamAlias
from ysr.scrapers.base import ScrapedGame


@dataclass(frozen=True)
class IngestResult:
    inserted: int
    updated: int
    unchanged: int
    teams_created: int


@dataclass(frozen=True)
class EventIngestResult:
    flights_ingested: int
    flights_failed: int
    inserted: int
    updated: int
    unchanged: int
    teams_created: int


def get_or_create_source(
    session: Session, name: str, base_url: str, scraper_module: str
) -> Source:
    existing = session.scalar(select(Source).where(Source.name == name))
    if existing is not None:
        return existing
    source = Source(name=name, base_url=base_url, scraper_module=scraper_module)
    session.add(source)
    session.flush()
    return source


def mark_source_run(session: Session, source: Source, status: str) -> None:
    # Source.last_run is a naive DateTime column; store naive UTC.
    source.last_run = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    source.status = status
    session.flush()


def _resolve_team(
    session: Session,
    source_id: int,
    source_team_id: str,
    name: str,
    club: str | None,
    birth_year: int,
    gender: str,
) -> tuple[Team, bool]:
    alias = session.scalar(
        select(TeamAlias).where(
            TeamAlias.source_id == source_id,
            TeamAlias.alias_name == source_team_id,
        )
    )
    if alias is not None:
        team = session.get(Team, alias.team_id)
        assert team is not None
        return team, False

    team = Team(display_name=name, club=club, birth_year=birth_year, gender=gender)
    session.add(team)
    session.flush()
    session.add(TeamAlias(alias_name=source_team_id, source_id=source_id, team_id=team.id))
    session.flush()
    return team, True


def _upsert_game(
    session: Session, source_id: int, game: ScrapedGame, home_id: int, away_id: int
) -> str:
    existing = session.scalar(
        select(Game).where(
            Game.source_id == source_id,
            Game.date == game.date,
            Game.home_team_id == home_id,
            Game.away_team_id == away_id,
        )
    )
    if existing is None:
        session.add(
            Game(
                source_id=source_id,
                date=game.date,
                home_team_id=home_id,
                away_team_id=away_id,
                home_score=game.home_score,
                away_score=game.away_score,
                competition=game.competition,
                raw_payload=game.raw,
            )
        )
        return "inserted"
    if existing.home_score != game.home_score or existing.away_score != game.away_score:
        existing.home_score = game.home_score
        existing.away_score = game.away_score
        existing.raw_payload = game.raw
        return "updated"
    return "unchanged"


def ingest_games(
    session: Session,
    source_id: int,
    games: list[ScrapedGame],
    *,
    birth_year: int,
    gender: str,
) -> IngestResult:
    inserted = updated = unchanged = teams_created = 0
    for game in games:
        home, home_new = _resolve_team(
            session, source_id, game.home_source_id, game.home_team, game.home_club, birth_year, gender
        )
        away, away_new = _resolve_team(
            session, source_id, game.away_source_id, game.away_team, game.away_club, birth_year, gender
        )
        teams_created += int(home_new) + int(away_new)
        outcome = _upsert_game(session, source_id, game, home.id, away.id)
        if outcome == "inserted":
            inserted += 1
        elif outcome == "updated":
            updated += 1
        else:
            unchanged += 1
        session.flush()
    return IngestResult(inserted=inserted, updated=updated, unchanged=unchanged, teams_created=teams_created)
