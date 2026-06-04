from ysr.identity import Candidate, best_match, normalize_name


def test_normalize_lowercases_and_collapses_whitespace() -> None:
    assert normalize_name("  Strikers-FC   2010B ") == "strikers fc 2010b"


def test_best_match_returns_exact_candidate() -> None:
    candidates = [Candidate(team_id=1, name="Strikers FC"), Candidate(team_id=2, name="Surf SC")]
    result = best_match("strikers fc", candidates)
    assert result.team_id == 1
    assert result.score >= 99.0


def test_best_match_fuzzy_above_threshold() -> None:
    candidates = [Candidate(team_id=1, name="Strikers FC 2010 Boys")]
    result = best_match("Strikers FC 2010B", candidates, threshold=80.0)
    assert result.team_id == 1


def test_best_match_below_threshold_returns_none() -> None:
    candidates = [Candidate(team_id=1, name="Strikers FC")]
    result = best_match("Totally Different Club", candidates, threshold=85.0)
    assert result.team_id is None


def test_best_match_short_query_matches_longer_candidate() -> None:
    candidates = [Candidate(team_id=1, name="Strikers FC 2010 Boys")]
    result = best_match("Strikers FC", candidates)
    assert result.team_id == 1


def test_best_match_empty_candidates() -> None:
    result = best_match("anything", [])
    assert result.team_id is None
    assert result.score == 0.0
