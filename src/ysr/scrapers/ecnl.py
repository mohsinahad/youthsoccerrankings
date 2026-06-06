from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import Any

from ysr.scrapers.base import ScrapedGame
from ysr.scrapers.http import HttpClient

_BASE = "https://api.athleteone.com/api/Event"
_YEAR_RE = re.compile(r"(\d{4})")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlightRef:
    flight_id: int
    birth_year: int
    gender: str
    name: str


def fetch_event_tree(client: HttpClient, *, event_id: int) -> dict[str, Any]:
    url = f"{_BASE}/get-event-schedule-or-standings/{event_id}"
    payload = client.get_json(url)
    if payload.get("result") != "success":
        raise RuntimeError(
            f"AthleteOne API returned non-success for event {event_id}: "
            f"result={payload.get('result')!r} message={payload.get('message')!r}"
        )
    return payload


def parse_event_flights(tree: dict[str, Any]) -> list[FlightRef]:
    data = tree["data"]
    flights: list[FlightRef] = []
    for list_key, gender in (("boysDivAndFlightList", "M"), ("girlsDivAndFlightList", "F")):
        for division in data.get(list_key) or []:
            division_name = str(division.get("divisionName", ""))
            year_match = _YEAR_RE.search(division_name)
            if year_match is None:
                logger.warning("skipping division %r: no birth year in name", division_name)
                continue
            birth_year = int(year_match.group(1))
            for flight in division.get("flightList") or []:
                if not flight.get("hasActiveSchedule"):
                    continue
                flights.append(
                    FlightRef(
                        flight_id=int(flight["flightID"]),
                        birth_year=birth_year,
                        gender=gender,
                        name=str(flight.get("flightName", "")),
                    )
                )
    return flights


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


def _parse_match(match: dict[str, Any]) -> ScrapedGame | None:
    home_score = match.get("hometeamscore")
    away_score = match.get("awayteamscore")
    if home_score is None or away_score is None:
        return None  # unplayed — skip, not an error
    return ScrapedGame(
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


def parse_division(payload: dict[str, Any]) -> list[ScrapedGame]:
    games: list[ScrapedGame] = []
    for match in payload["data"]:
        try:
            game = _parse_match(match)
        except Exception:
            logger.warning(
                "skipping malformed match %r", match.get("matchID"), exc_info=True
            )
            continue
        if game is not None:
            games.append(game)
    return games
