import datetime as dt

from ysr.web.season import season_end_year, u_age


def test_season_end_year_rolls_over_on_august() -> None:
    assert season_end_year(dt.date(2026, 6, 1)) == 2026
    assert season_end_year(dt.date(2026, 7, 31)) == 2026
    assert season_end_year(dt.date(2026, 8, 1)) == 2027


def test_u_age_current_season() -> None:
    today = dt.date(2026, 6, 1)
    assert u_age(2014, today) == 12
    assert u_age(2013, today) == 13
    assert u_age(2012, today) == 14


def test_u_age_rolls_next_season() -> None:
    assert u_age(2013, dt.date(2026, 8, 1)) == 14
