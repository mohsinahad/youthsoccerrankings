import dataclasses
import datetime as dt

from ysr.scrapers.base import ScrapedGame


def test_scraped_game_holds_fields_and_is_frozen() -> None:
    g = ScrapedGame(
        date=dt.date(2024, 8, 18),
        home_source_id="69758",
        home_team="Pittsburgh Riverhounds - Pre ECNL B13",
        home_club="Pittsburgh Riverhounds",
        away_source_id="93515",
        away_team="Manta United Soccer Club - Manta 2013 Boys Pink",
        away_club="Manta United Soccer Club",
        home_score=2,
        away_score=2,
        competition="U12 (2013) Pre-ECNL North - 9v9",
        raw={"matchID": 675970},
    )
    assert g.home_source_id == "69758"
    assert g.away_club == "Manta United Soccer Club"
    assert g.home_score == 2
    assert dataclasses.is_dataclass(g)
