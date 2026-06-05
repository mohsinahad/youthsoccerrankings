import math

from ysr.ranking.glicko2 import Glicko, rate


def test_rate_matches_glickman_paper_example() -> None:
    # Worked example from Glickman's Glicko-2 paper.
    player = Glicko(1500.0, 200.0, 0.06)
    results = [
        (Glicko(1400.0, 30.0), 1.0),
        (Glicko(1550.0, 100.0), 0.0),
        (Glicko(1700.0, 300.0), 0.0),
    ]
    new = rate(player, results)
    assert abs(new.rating - 1464.05) < 0.5
    assert abs(new.rd - 151.52) < 0.5
    assert abs(new.vol - 0.05999) < 1e-4


def test_rate_no_results_inflates_rd_only() -> None:
    player = Glicko(1500.0, 200.0, 0.06)
    new = rate(player, [])
    assert new.rating == 1500.0
    assert new.vol == 0.06
    expected_rd = 173.7178 * math.sqrt((200.0 / 173.7178) ** 2 + 0.06**2)
    assert abs(new.rd - expected_rd) < 1e-6


def test_rate_winner_ends_above_loser() -> None:
    a = rate(Glicko(), [(Glicko(), 1.0)])
    b = rate(Glicko(), [(Glicko(), 0.0)])
    assert a.rating > b.rating
