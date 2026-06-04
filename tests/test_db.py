from sqlalchemy import select

from ysr.db import create_all, make_engine, make_session_factory
from ysr.models import Source


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
