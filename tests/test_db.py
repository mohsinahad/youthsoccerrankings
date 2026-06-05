import pytest
from sqlalchemy import select

from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Source


@pytest.mark.parametrize(
    ("given", "expected_driver"),
    [
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg"),
        ("postgres://u:p@host:5432/db", "postgresql+psycopg"),
        ("postgresql+psycopg://u:p@host:5432/db", "postgresql+psycopg"),
    ],
)
def test_make_engine_normalizes_postgres_driver(given: str, expected_driver: str) -> None:
    # Managed Postgres (Replit/Neon, Heroku) hands out postgres:// or postgresql://;
    # we need the psycopg3 driver. create_engine is lazy, so no DB connection is made.
    engine = make_engine(given)
    assert engine.url.drivername == expected_driver


def test_make_engine_preserves_query_params() -> None:
    engine = make_engine("postgresql://u:p@host/db?sslmode=require")
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.query.get("sslmode") == "require"


def test_session_factory_round_trip() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    create_all(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as s:
        s.add(Source(name="ECNL", base_url="x", scraper_module="m"))
        s.commit()

    with session_factory() as s:
        loaded = s.scalar(select(Source).where(Source.name == "ECNL"))
        assert loaded is not None
