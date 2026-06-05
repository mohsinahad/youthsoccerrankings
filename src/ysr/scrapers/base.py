from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScrapedGame:
    date: dt.date
    home_source_id: str
    home_team: str
    home_club: str | None
    away_source_id: str
    away_team: str
    away_club: str | None
    home_score: int
    away_score: int
    competition: str | None
    raw: dict[str, Any]
