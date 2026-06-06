from __future__ import annotations

import argparse
import logging

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ysr.db import make_engine, make_session_factory
from ysr.ingest import EventIngestResult, get_or_create_source, ingest_games, mark_source_run
from ysr.scrapers.ecnl import (
    FlightRef,
    fetch_division,
    fetch_event_tree,
    parse_division,
    parse_event_flights,
)
from ysr.scrapers.http import HttpClient

logger = logging.getLogger(__name__)

_REQUIRED_TABLES = ("sources", "games", "teams", "team_aliases")


def _ingest_flights(
    session: Session,
    source_id: int,
    client: HttpClient,
    event_id: int,
    flights: list[FlightRef],
) -> EventIngestResult:
    ingested = failed = inserted = updated = unchanged = teams = 0
    for flight in flights:
        try:
            payload = fetch_division(client, event_id=event_id, flight_id=flight.flight_id)
            games = parse_division(payload)
            result = ingest_games(
                session, source_id, games, birth_year=flight.birth_year, gender=flight.gender
            )
            session.commit()
            ingested += 1
            inserted += result.inserted
            updated += result.updated
            unchanged += result.unchanged
            teams += result.teams_created
        except Exception:
            session.rollback()
            failed += 1
            logger.warning("flight %s (%s) failed", flight.flight_id, flight.name, exc_info=True)
    return EventIngestResult(ingested, failed, inserted, updated, unchanged, teams)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ysr-scrape")
    sub = parser.add_subparsers(dest="source", required=True)
    ecnl = sub.add_parser("ecnl", help="Ingest ECNL flights for an event from AthleteOne/TGS")
    ecnl.add_argument("--event", type=int, required=True)
    ecnl.add_argument("--flight", type=int, default=None, help="optional: only this flight id")
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
        session.commit()
        client = HttpClient()
        try:
            tree = fetch_event_tree(client, event_id=args.event)
            flights = parse_event_flights(tree)
            if args.flight is not None:
                flights = [f for f in flights if f.flight_id == args.flight]
            result = _ingest_flights(session, source.id, client, args.event, flights)
            mark_source_run(session, source, "ok")
            session.commit()
        except Exception:
            session.rollback()
            mark_source_run(session, source, "error")
            session.commit()
            raise

    print(
        f"event {args.event}: ingested {result.flights_ingested} flights "
        f"({result.flights_failed} failed) — {result.inserted} new, {result.updated} updated, "
        f"{result.unchanged} unchanged, {result.teams_created} teams"
    )
    return 0
