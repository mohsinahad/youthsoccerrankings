from __future__ import annotations

import datetime as dt


def season_end_year(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    # US Soccer seasonal year runs Aug 1 - Jul 31; it's labeled by the calendar year it ends.
    return today.year if today.month <= 7 else today.year + 1


def u_age(birth_year: int, today: dt.date | None = None) -> int:
    return season_end_year(today) - birth_year
