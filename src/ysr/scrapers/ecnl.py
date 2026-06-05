from __future__ import annotations

import datetime as dt
from typing import Any

from ysr.scrapers.base import ScrapedGame
from ysr.scrapers.http import HttpClient

_BASE = "https://api.athleteone.com/api/Event"


def fetch_division(client: HttpClient, *, event_id: int, flight_id: int) -> dict[str, Any]:
    # teamID=0 returns every game in the flight (confirmed by the Task 1 spike).
    url = f"{_BASE}/get-schedules-by-flight/{event_id}/{flight_id}/0"
    payload = client.get_json(url)
    if payload.get("result") != "success":
        raise RuntimeError(
            f"AthleteOne API returned non-success for event {event_id} flight {flight_id}: "
            f"result={payload.get('result')!r} message={payload.get('message')!r}"
        )
    return payload


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
