from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ysr.models import Game, Rating, RatingHistory, Team
from ysr.web.season import u_age


@dataclass(frozen=True)
class Pool:
    birth_year: int
    gender: str
    u_age: int
    team_count: int


@dataclass(frozen=True)
class RankedTeam:
    rank: int
    team_id: int
    display_name: str
    club: str | None
    rating: float
    rd: float
    is_provisional: bool
    wins: int
    draws: int
    losses: int


@dataclass(frozen=True)
class HistoryPoint:
    computed_at: dt.datetime
    rating: float


@dataclass(frozen=True)
class ResultRow:
    date: dt.date
    opponent: str
    our_score: int
    their_score: int
    outcome: str  # "W" | "D" | "L"


@dataclass(frozen=True)
class TeamDetail:
    team: RankedTeam
    birth_year: int
    gender: str
    u_age: int
    history: list[HistoryPoint]
    results: list[ResultRow]


def list_pools(session: Session) -> list[Pool]:
    rows = (
        session.execute(
            select(Team.birth_year, Team.gender, func.count(Team.id))
            .join(Rating, Rating.team_id == Team.id)
            .group_by(Team.birth_year, Team.gender)
            .order_by(Team.birth_year, Team.gender)
        )
        .tuples()
        .all()
    )
    return [Pool(birth_year=by, gender=g, u_age=u_age(by), team_count=n) for by, g, n in rows]


def _records(games: list[Game], team_ids: list[int]) -> dict[int, tuple[int, int, int]]:
    tally: dict[int, list[int]] = {tid: [0, 0, 0] for tid in team_ids}  # [w, d, l]
    for g in games:
        if g.home_score > g.away_score:
            tally[g.home_team_id][0] += 1
            tally[g.away_team_id][2] += 1
        elif g.home_score < g.away_score:
            tally[g.home_team_id][2] += 1
            tally[g.away_team_id][0] += 1
        else:
            tally[g.home_team_id][1] += 1
            tally[g.away_team_id][1] += 1
    return {tid: (v[0], v[1], v[2]) for tid, v in tally.items()}


def pool_rankings(session: Session, birth_year: int, gender: str) -> list[RankedTeam]:
    teams = list(
        session.scalars(
            select(Team).where(Team.birth_year == birth_year, Team.gender == gender)
        ).all()
    )
    team_by_id = {t.id: t for t in teams}
    ratings = {
        r.team_id: r
        for r in session.scalars(
            select(Rating).where(Rating.team_id.in_(list(team_by_id)))
        ).all()
    }
    rated_ids = [tid for tid in team_by_id if tid in ratings]
    games = list(
        session.scalars(
            select(Game).where(
                Game.home_team_id.in_(rated_ids), Game.away_team_id.in_(rated_ids)
            )
        ).all()
    )
    records = _records(games, rated_ids)

    ordered = sorted(
        (ratings[tid] for tid in rated_ids),
        key=lambda r: (-r.rating, r.rating_deviation, r.team_id),
    )
    ranked: list[RankedTeam] = []
    for i, r in enumerate(ordered, start=1):
        team = team_by_id[r.team_id]
        wins, draws, losses = records.get(r.team_id, (0, 0, 0))
        ranked.append(
            RankedTeam(
                rank=i,
                team_id=r.team_id,
                display_name=team.display_name,
                club=team.club,
                rating=r.rating,
                rd=r.rating_deviation,
                is_provisional=r.is_provisional,
                wins=wins,
                draws=draws,
                losses=losses,
            )
        )
    return ranked


def team_detail(session: Session, team_id: int) -> TeamDetail | None:
    team = session.get(Team, team_id)
    if team is None:
        return None
    ranked = pool_rankings(session, team.birth_year, team.gender)
    me = next((rt for rt in ranked if rt.team_id == team_id), None)
    if me is None:
        return None

    history = [
        HistoryPoint(computed_at=h.computed_at, rating=h.rating)
        for h in session.scalars(
            select(RatingHistory)
            .where(RatingHistory.team_id == team_id)
            .order_by(RatingHistory.computed_at)
        ).all()
    ]

    games = session.scalars(
        select(Game)
        .where(or_(Game.home_team_id == team_id, Game.away_team_id == team_id))
        .order_by(Game.date.desc())
    ).all()
    results: list[ResultRow] = []
    for g in games:
        is_home = g.home_team_id == team_id
        opponent_id = g.away_team_id if is_home else g.home_team_id
        opponent = session.get(Team, opponent_id)
        our = g.home_score if is_home else g.away_score
        their = g.away_score if is_home else g.home_score
        outcome = "W" if our > their else ("L" if our < their else "D")
        results.append(
            ResultRow(
                date=g.date,
                opponent=opponent.display_name if opponent else "Unknown",
                our_score=our,
                their_score=their,
                outcome=outcome,
            )
        )
    return TeamDetail(
        team=me,
        birth_year=team.birth_year,
        gender=team.gender,
        u_age=u_age(team.birth_year),
        history=history,
        results=results,
    )
