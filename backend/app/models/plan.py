"""Plan tables.

Defined here so the initial migration carries the full schema from the README's
data model. No generation logic lives in the codebase yet — that is M4.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONColumn


class Plan(Base):
    __tablename__ = "plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athlete.id", ondelete="CASCADE"), index=True
    )
    goal_time_s: Mapped[int] = mapped_column(Integer)
    race_date: Mapped[date] = mapped_column(Date)
    start_date: Mapped[date] = mapped_column(Date)
    weeks: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    engine_version: Mapped[str] = mapped_column(String(32))
    superseded_by: Mapped[int | None] = mapped_column(ForeignKey("plan.id", ondelete="SET NULL"))

    #: Derivation kept with the plan: pace table, warnings, peak targets.
    meta: Mapped[dict | None] = mapped_column(JSONColumn)

    sessions: Mapped[list["PlanSession"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanSession(Base):
    __tablename__ = "plan_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan.id", ondelete="CASCADE"), index=True)
    week_no: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[int] = mapped_column(Integer)
    date: Mapped[date] = mapped_column(Date, index=True)
    session_type: Mapped[str] = mapped_column(String(40))

    target_distance_m: Mapped[float | None] = mapped_column(Float)
    target_pace_low: Mapped[float | None] = mapped_column(Float)
    target_pace_high: Mapped[float | None] = mapped_column(Float)
    structure: Mapped[dict | None] = mapped_column(JSONColumn)
    notes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(16), default="planned")
    matched_activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activity.id", ondelete="SET NULL")
    )

    plan: Mapped[Plan] = relationship(back_populates="sessions")
