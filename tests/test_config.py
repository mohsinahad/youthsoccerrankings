from pytest import MonkeyPatch

from ysr.config import Settings


def test_default_database_url_is_sqlite_memory() -> None:
    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///:memory:"


def test_database_url_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@host/db"
