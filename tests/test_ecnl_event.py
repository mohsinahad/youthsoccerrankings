import json
import logging
import pathlib

import httpx
import pytest

from ysr.scrapers.ecnl import fetch_event_tree, parse_event_flights
from ysr.scrapers.http import HttpClient

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_tree.json"


def test_parse_event_flights_from_real_tree() -> None:
    tree = json.loads(FIXTURE.read_text())
    flights = parse_event_flights(tree)
    assert [f.flight_id for f in flights] == [26840, 26847, 26838, 26839]
    assert [f.birth_year for f in flights] == [2013, 2013, 2014, 2014]
    assert all(f.gender == "M" for f in flights)


def test_parse_event_flights_gender_active_and_age_filters() -> None:
    tree = {
        "data": {
            "boysDivAndFlightList": [
                {
                    "divisionID": 1,
                    "divisionName": "B2013",
                    "flightList": [
                        {"flightID": 100, "flightName": "U12 (2013) North", "hasActiveSchedule": True},
                        {"flightID": 101, "flightName": "U12 (2013) Inactive", "hasActiveSchedule": False},
                        {"flightID": 102, "flightName": "Showcase only", "hasActiveSchedule": True},
                    ],
                }
            ],
            "girlsDivAndFlightList": [
                {
                    "divisionID": 2,
                    "divisionName": "G2013",
                    "flightList": [
                        {"flightID": 200, "flightName": "U12 (2013) Girls North", "hasActiveSchedule": True}
                    ],
                }
            ],
        }
    }
    by_id = {f.flight_id: f for f in parse_event_flights(tree)}
    # 101 is inactive (excluded); 102 is included because the birth year comes from the
    # division name ("B2013"), not the flight name.
    assert set(by_id) == {100, 102, 200}
    assert by_id[100].gender == "M" and by_id[100].birth_year == 2013
    assert by_id[102].birth_year == 2013
    assert by_id[200].gender == "F" and by_id[200].birth_year == 2013


def test_parse_event_flights_skips_division_without_birth_year(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tree = {
        "data": {
            "boysDivAndFlightList": [
                {
                    "divisionName": "Boys Pre-ECNL",
                    "flightList": [{"flightID": 9, "flightName": "North", "hasActiveSchedule": True}],
                }
            ],
            "girlsDivAndFlightList": [],
        }
    }
    with caplog.at_level(logging.WARNING):
        assert parse_event_flights(tree) == []
    assert "Boys Pre-ECNL" in caplog.text


def test_fetch_event_tree_raises_on_non_success() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"result": "error"}))
    client = HttpClient(client=httpx.Client(transport=transport), min_interval=0.0)
    with pytest.raises(RuntimeError, match="non-success"):
        fetch_event_tree(client, event_id=3210)
