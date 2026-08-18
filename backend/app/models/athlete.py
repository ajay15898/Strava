from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONColumn


class Athlete(Base):
    __tablename__ = "athlete"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strava_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    max_hr: Mapped[int | None] = mapped_column(Integer)
    ftp: Mapped[int | None] = mapped_column(Integer)
    measurement_pref: Mapped[str] = mapped_column(String(16), default="metric")

    goal_race_distance_m: Mapped[float | None] = mapped_column()
    goal_time_s: Mapped[int | None] = mapped_column(Integer)
    goal_race_date: Mapped[datetime | None] = mapped_column(Date)

    # Athlete constraint rather than a planner assumption — history shows 2-3
    # runs/week, so the engine must be told what is actually available.
    max_sessions_per_week: Mapped[int | None] = mapped_column(Integer)

    #: Weekly session pattern — training days, and which sessions are fixed
    #: commitments the engine must plan around rather than size.
    preferences: Mapped[dict | None] = mapped_column(JSONColumn)

    token: Mapped["OAuthToken | None"] = relationship(
        back_populates="athlete", uselist=False, cascade="all, delete-orphan"
    )


class OAuthToken(Base):
    __tablename__ = "oauth_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athlete.id", ondelete="CASCADE"), unique=True, index=True
    )
    access_token: Mapped[str] = mapped_column(String(255))
    refresh_token: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str | None] = mapped_column(String(255))

    athlete: Mapped[Athlete] = relationship(back_populates="token")
