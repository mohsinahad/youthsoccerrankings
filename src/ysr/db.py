from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ysr.config import get_settings
from ysr.models import Base


def _normalize_db_url(url: str) -> str:
    # Managed Postgres (Replit/Neon, Heroku) hands out postgres:// or postgresql://;
    # our engine uses psycopg3, which needs the +psycopg driver. Leave anything that
    # already names a driver (or isn't Postgres, e.g. sqlite) untouched.
    if url.startswith(("postgresql+", "postgres+")):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def make_engine(url: str | None = None) -> Engine:
    resolved = _normalize_db_url(url or get_settings().database_url)
    if resolved == "sqlite+pysqlite:///:memory:":
        return create_engine(
            resolved,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(resolved)


def create_all(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
