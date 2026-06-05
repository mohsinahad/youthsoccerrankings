from __future__ import annotations

import datetime as dt
from typing import Any

from ysr.scrapers.base import ScrapedGame


def _parse_date(value: str) -> dt.date:
    return dt.datetime.fromisoformat(value).date()


def parse_division(payload: dict[str, Any]) -> list[ScrapedGame]:
    games: list[ScrapedGame] = []
    for match in payload["data"]:
        home_score = match.get("hometeamscore")
        away_score = match.get("awayteamscore")
        if home_score is None or away_score is None:
            continue  # unplayed — skip
        games.append(
            ScrapedGame(
                date=_parse_date(match["gameDate"]),
                home_source_id=str(match["hometeamID"]),
                home_team=match["homeTeam"],
                home_club=match.get("homeTeamClub"),
                away_source_id=str(match["awayteamID"]),
                away_team=match["awayTeam"],
                away_club=match.get("awayTeamClub"),
                home_score=int(home_score),
                away_score=int(away_score),
                competition=match.get("flight"),
                raw=match,
            )
        )
    return games
