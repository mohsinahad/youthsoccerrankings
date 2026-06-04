from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    base_url: Mapped[str] = mapped_column(String)
    scraper_module: Mapped[str] = mapped_column(String)
    last_run: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="idle")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String)
    club: Mapped[str | None] = mapped_column(String, nullable=True)
    age_group: Mapped[str] = mapped_column(String)
    gender: Mapped[str] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)

    aliases: Mapped[list[TeamAlias]] = relationship(back_populates="team")


class TeamAlias(Base):
    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("alias_name", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alias_name: Mapped[str] = mapped_column(String)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    team: Mapped[Team] = relationship(back_populates="aliases")


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("source_id", "date", "home_team_id", "away_team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    date: Mapped[dt.date] = mapped_column(Date)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    competition: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("team_id", "age_group", "gender"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    age_group: Mapped[str] = mapped_column(String)
    gender: Mapped[str] = mapped_column(String)
    rating: Mapped[float] = mapped_column(Float)
    rating_deviation: Mapped[float] = mapped_column(Float)
    volatility: Mapped[float] = mapped_column(Float)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime)


class RatingHistory(Base):
    __tablename__ = "rating_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    rating: Mapped[float] = mapped_column(Float)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime)
