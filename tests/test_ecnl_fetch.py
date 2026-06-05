import json
import pathlib

import httpx

from ysr.scrapers.ecnl import fetch_division, parse_division
from ysr.scrapers.http import HttpClient

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ecnl_event_sample.json"


def test_fetch_division_calls_endpoint_and_returns_payload() -> None:
    body = json.loads(FIXTURE.read_text())
    captured: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json=body)

    client = HttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval=0.0)
    payload = fetch_division(client, event_id=3210, flight_id=26840)

    assert "get-schedules-by-flight/3210/26840/0" in captured["url"]
    assert len(parse_division(payload)) == 2
