from __future__ import annotations

import time
from typing import Any, cast

import httpx

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://public.totalglobalsports.com",
}


class HttpClient:
    def __init__(self, *, client: httpx.Client | None = None, min_interval: float = 1.0) -> None:
        self._client = client or httpx.Client(headers=_DEFAULT_HEADERS, timeout=30.0)
        self._min_interval = min_interval
        self._last_request = 0.0

    def get_json(self, url: str, *, retries: int = 3) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(retries):
            self._respect_rate_limit()
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                return cast(dict[str, Any], resp.json())
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"GET {url} failed after {retries} attempts") from last_exc

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()
