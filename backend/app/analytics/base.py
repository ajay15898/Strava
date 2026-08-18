"""The canonical definition of an analysable run.

Every analytic imports `valid_runs` rather than writing its own filter. The
2026 baseline had a phantom training day because the noise floor was applied to
distance totals but not to day counting; defining the filter exactly once is
what stops that class of bug recurring.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.constants import NOISE_FLOOR_M, RUN_SPORT_TYPES
from app.models import Activity


def runs_query(athlete_id: int, start: date | None = None, end: date | None = None) -> Select:
    stmt = select(Activity).where(
        Activity.athlete_id == athlete_id,
        Activity.is_duplicate.is_(False),
        Activity.sport_type.in_(RUN_SPORT_TYPES),
        Activity.distance_m >= NOISE_FLOOR_M,
    )
    if start is not None:
        stmt = stmt.where(Activity.start_local >= datetime.combine(start, datetime.min.time()))
    if end is not None:
        stmt = stmt.where(Activity.start_local <= datetime.combine(end, datetime.max.time()))
    return stmt.order_by(Activity.start_local)


def valid_runs(
    db: Session, athlete_id: int, start: date | None = None, end: date | None = None
) -> list[Activity]:
    return list(db.scalars(runs_query(athlete_id, start, end)).all())


def run_days(runs: list[Activity]) -> set[date]:
    """Distinct calendar days containing at least one analysable run."""
    return {r.start_local.date() for r in runs}


def total_km(runs: list[Activity]) -> float:
    return sum(r.distance_m for r in runs) / 1000.0
