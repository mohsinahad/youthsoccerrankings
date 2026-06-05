import httpx
import pytest

from ysr.scrapers.http import HttpClient


def test_get_json_returns_parsed_body() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))
    client = HttpClient(client=httpx.Client(transport=transport), min_interval=0.0)
    assert client.get_json("https://example.test/api") == {"ok": True}


def test_get_json_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ysr.scrapers.http.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval=0.0)
    assert client.get_json("https://example.test/api") == {"ok": True}
    assert calls["n"] == 2


def test_get_json_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ysr.scrapers.http.time.sleep", lambda _s: None)
    transport = httpx.MockTransport(lambda req: httpx.Response(503))
    client = HttpClient(client=httpx.Client(transport=transport), min_interval=0.0)
    with pytest.raises(RuntimeError):
        client.get_json("https://example.test/api", retries=3)
