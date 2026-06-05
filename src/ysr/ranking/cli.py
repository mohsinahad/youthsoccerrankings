from __future__ import annotations

import argparse

from sqlalchemy import inspect

from ysr.db import make_engine, make_session_factory
from ysr.ranking.engine import recompute_all

_REQUIRED_TABLES = ("teams", "games", "ratings", "rating_history")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="ysr-rank", description="Recompute all team rankings"
    ).parse_args(argv)

    engine = make_engine()
    existing = set(inspect(engine).get_table_names())
    missing = [t for t in _REQUIRED_TABLES if t not in existing]
    if missing:
        raise RuntimeError(
            f"database not initialized (missing tables: {', '.join(missing)}); "
            "run `alembic upgrade head`"
        )

    with make_session_factory(engine)() as session:
        result = recompute_all(session)
        session.commit()

    print(
        f"ranked {result.teams_rated} teams across {result.pools} pools, "
        f"wrote {result.history_rows} history rows"
    )
    return 0
