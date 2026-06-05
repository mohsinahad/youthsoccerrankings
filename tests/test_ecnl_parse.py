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
