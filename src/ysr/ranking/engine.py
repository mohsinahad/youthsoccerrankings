from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ysr.models import Game, Rating, RatingHistory, Team
from ysr.ranking.glicko2 import Glicko, rate

_PROVISIONAL_RD_THRESHOLD = 100.0


@dataclass(frozen=True)
class RankingRunResult:
    pools: int
    teams_rated: int
    history_rows: int


def _score(home_score: int, away_score: int, *, is_home: bool) -> float:
    mine, theirs = (home_score, away_score) if is_home else (away_score, home_score)
    if mine > theirs:
        return 1.0
    if mine < theirs:
        return 0.0
    return 0.5


def _upsert_rating(session: Session, team_id: int, g: Glicko, now: dt.datetime) -> None:
    is_provisional = g.rd > _PROVISIONAL_RD_THRESHOLD
    existing = session.scalar(select(Rating).where(Rating.team_id == team_id))
    if existing is None:
        session.add(
            Rating(
                team_id=team_id,
                rating=g.rating,
                rating_deviation=g.rd,
                volatility=g.vol,
                is_provisional=is_provisional,
                computed_at=now,
            )
        )
    else:
        existing.rating = g.rating
        existing.rating_deviation = g.rd
        existing.volatility = g.vol
        existing.is_provisional = is_provisional
        existing.computed_at = now


def recompute_all(session: Session) -> RankingRunResult:
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    pools = session.execute(select(Team.birth_year, Team.gender).distinct()).tuples().all()

    pools_rated = 0
    teams_rated = 0
    history_rows = 0
    for birth_year, gender in pools:
        team_ids = list(
            session.scalars(
                select(Team.id).where(Team.birth_year == birth_year, Team.gender == gender)
            ).all()
        )
        games = list(
            session.scalars(
                select(Game).where(
                    Game.home_team_id.in_(team_ids),
                    Game.away_team_id.in_(team_ids),
                )
            ).all()
        )
        if not games:
            continue

        results: dict[int, list[tuple[Glicko, float]]] = {}
        for game in games:
            results.setdefault(game.home_team_id, []).append(
                (Glicko(), _score(game.home_score, game.away_score, is_home=True))
            )
            results.setdefault(game.away_team_id, []).append(
                (Glicko(), _score(game.home_score, game.away_score, is_home=False))
            )

        pools_rated += 1
        for team_id, team_results in results.items():
            new = rate(Glicko(), team_results)
            _upsert_rating(session, team_id, new, now)
            session.add(RatingHistory(team_id=team_id, rating=new.rating, computed_at=now))
            teams_rated += 1
            history_rows += 1
        session.flush()

    return RankingRunResult(pools=pools_rated, teams_rated=teams_rated, history_rows=history_rows)
