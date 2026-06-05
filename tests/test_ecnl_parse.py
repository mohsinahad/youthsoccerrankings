import datetime as dt
import json
import pathlib

from ysr.scrapers.ecnl import parse_division

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def test_parse_division_maps_completed_games_only() -> None:
    payload = json.loads(FIXTURE.read_text())
    games = parse_division(payload)

    # Fixture has 3 records: 2 played, 1 unplayed (null scores) -> only the 2 played parse.
    assert len(games) == 2
    for g in games:
        assert isinstance(g.date, dt.date)
        assert g.home_source_id and g.away_source_id
        assert g.home_team and g.away_team
        assert isinstance(g.home_score, int) and isinstance(g.away_score, int)
        assert g.raw

    g = games[0]
    assert g.home_source_id == "69758"
    assert g.home_club == "Pittsburgh Riverhounds"
    assert g.competition == "U12 (2013) Pre-ECNL North - 9v9"


import logging


def test_parse_division_skips_malformed_record_and_logs(caplog) -> None:  # type: ignore[no-untyped-def]
    good = {
        "gameDate": "2024-08-18T11:00:00",
        "homeTeam": "A",
        "awayTeam": "B",
        "hometeamID": 1,
        "awayteamID": 2,
        "homeTeamClub": "A Club",
        "awayTeamClub": "B Club",
        "hometeamscore": 3,
        "awayteamscore": 1,
        "flight": "U16 Boys",
    }
    # Played (scores present) but missing required "homeTeam" -> parse error, not an unplayed game.
    bad = {
        "gameDate": "2024-08-18T11:00:00",
        "awayTeam": "B",
        "hometeamID": 1,
        "awayteamID": 2,
        "hometeamscore": 3,
        "awayteamscore": 1,
        "flight": "U16 Boys",
        "matchID": 99999,
    }
    with caplog.at_level(logging.WARNING):
        games = parse_division({"data": [good, bad]})

    assert len(games) == 1
    assert games[0].home_team == "A"
    assert "99999" in caplog.text
