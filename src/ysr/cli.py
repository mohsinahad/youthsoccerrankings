from __future__ import annotations

import argparse

from sqlalchemy import inspect

from ysr.db import make_engine, make_session_factory
from ysr.ingest import get_or_create_source, ingest_games, mark_source_run
from ysr.scrapers.ecnl import fetch_division, parse_division
from ysr.scrapers.http import HttpClient

_REQUIRED_TABLES = ("sources", "games", "teams", "team_aliases")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ysr-scrape")
    sub = parser.add_subparsers(dest="source", required=True)
    ecnl = sub.add_parser("ecnl", help="Ingest one ECNL flight from AthleteOne/TGS")
    ecnl.add_argument("--event", type=int, required=True)
    ecnl.add_argument("--flight", type=int, required=True)
    ecnl.add_argument("--age-group", required=True)
    ecnl.add_argument("--gender", required=True, choices=["M", "F"])
    args = parser.parse_args(argv)

    engine = make_engine()
    existing = set(inspect(engine).get_table_names())
    missing = [t for t in _REQUIRED_TABLES if t not in existing]
    if missing:
        raise RuntimeError(
            f"database not initialized (missing tables: {', '.join(missing)}); "
            "run `alembic upgrade head`"
        )

    session_factory = make_session_factory(engine)
    with session_factory() as session:
        source = get_or_create_source(
            session, "ECNL", "https://www.totalglobalsports.com/ecnl/", "ysr.scrapers.ecnl"
        )
        session.commit()  # persist the source row so run status survives a later failure
        try:
            payload = fetch_division(HttpClient(), event_id=args.event, flight_id=args.flight)
            games = parse_division(payload)
            result = ingest_games(
                session, source.id, games, age_group=args.age_group, gender=args.gender
            )
            mark_source_run(session, source, "ok")
            session.commit()
        except Exception:
            session.rollback()
            mark_source_run(session, source, "error")
            session.commit()
            raise

    print(
        f"ingested: {result.inserted} new, {result.updated} updated, "
        f"{result.unchanged} unchanged, {result.teams_created} teams created"
    )
    return 0
