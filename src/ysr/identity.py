from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process


@dataclass(frozen=True)
class Candidate:
    team_id: int
    name: str


@dataclass(frozen=True)
class MatchResult:
    team_id: int | None
    score: float


def normalize_name(name: str) -> str:
    return " ".join(name.lower().replace("-", " ").split())


def best_match(
    query: str,
    candidates: list[Candidate],
    threshold: float = 85.0,
) -> MatchResult:
    if not candidates:
        return MatchResult(team_id=None, score=0.0)

    choices = {c.team_id: normalize_name(c.name) for c in candidates}
    match = process.extractOne(
        normalize_name(query),
        choices,
        scorer=fuzz.token_set_ratio,
    )
    if match is None:
        return MatchResult(team_id=None, score=0.0)

    _value, score, key = match
    if score >= threshold:
        return MatchResult(team_id=key, score=score)
    return MatchResult(team_id=None, score=score)
