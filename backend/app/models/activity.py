from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONColumn


class Activity(Base):
    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strava_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athlete.id", ondelete="CASCADE"), index=True
    )

    sport_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str | None] = mapped_column(String(255))

    start_local: Mapped[datetime] = mapped_column(DateTime, index=True)
    start_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    distance_m: Mapped[float] = mapped_column(Float, default=0.0)
    moving_time_s: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_time_s: Mapped[int] = mapped_column(Integer, default=0)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    avg_speed: Mapped[float | None] = mapped_column(Float)
    max_speed: Mapped[float | None] = mapped_column(Float)

    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    has_heartrate: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_watts: Mapped[float | None] = mapped_column(Float)
    has_device_watts: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_cadence: Mapped[float | None] = mapped_column(Float)

    calories: Mapped[float | None] = mapped_column(Float)
    relative_effort: Mapped[float | None] = mapped_column(Float)
    pr_count: Mapped[int | None] = mapped_column(Integer)
    achievement_count: Mapped[int | None] = mapped_column(Integer)
    gear_id: Mapped[str | None] = mapped_column(String(64))
    polyline: Mapped[str | None] = mapped_column(Text)

    # Never hard-deleted; the flag stays queryable so volume can be audited
    # with and without the duplicate recordings.
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    duplicate_of_strava_id: Mapped[int | None] = mapped_column(BigInteger)

    streams_fetched: Mapped[bool] = mapped_column(Boolean, default=False)

    streams: Mapped[list["ActivityStream"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    best_efforts: Mapped[list["BestEffort"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_activity_athlete_start", "athlete_id", "start_local"),)

    @property
    def pace_s_per_km(self) -> float | None:
        if self.distance_m <= 0 or self.moving_time_s <= 0:
            return None
        return self.moving_time_s / (self.distance_m / 1000.0)


class ActivityStream(Base):
    __tablename__ = "activity_stream"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSONColumn)

    activity: Mapped[Activity] = relationship(back_populates="streams")

    __table_args__ = (UniqueConstraint("activity_id", "type", name="uq_stream_activity_type"),)


class BestEffort(Base):
    """Strava's own per-activity best efforts (400 m through 30 K).

    These arrive on the activity detail payload and need no stream fetch, which
    is what makes the pace-at-distance curve an ingest-time artefact rather
    than something the analytics layer has to reconstruct from raw streams.
    """

    __tablename__ = "best_effort"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activity.id", ondelete="CASCADE"), index=True
    )
    strava_effort_id: Mapped[int | None] = mapped_column(BigInteger)
    effort_type: Mapped[str] = mapped_column(String(40), index=True)
    duration_s: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[float] = mapped_column(Float)

    activity: Mapped[Activity] = relationship(back_populates="best_efforts")

    __table_args__ = (
        UniqueConstraint("activity_id", "effort_type", name="uq_effort_activity_type"),
    )


class DailyLoad(Base):
    __tablename__ = "daily_load"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athlete.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    load: Mapped[float] = mapped_column(Float, default=0.0)
    ctl: Mapped[float] = mapped_column(Float, default=0.0)
    atl: Mapped[float] = mapped_column(Float, default=0.0)
    tsb: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (UniqueConstraint("athlete_id", "date", name="uq_load_athlete_date"),)
