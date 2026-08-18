"""Training load, and the CTL / ATL / TSB series derived from it.

Strava's Relative Effort is heart-rate derived, and this athlete's recent
activities carry no heart rate at all — the gap starts no later than
2026-07-11, not in August as first assumed. So load falls back to running TSS,
computed from pace against threshold pace:

    load = (duration_h) * IF^2 * 100,   IF = avg_speed / threshold_speed

Relative Effort is still preferred when Strava supplies it, so the series
degrades gracefully rather than switching wholesale between two scales.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.base import runs_query
from app.constants import ATL_DAYS, CTL_DAYS, DEFAULT_THRESHOLD_SPEED_MS
from app.models import Activity


@dataclass
class LoadDay:
    date: date
    load: float
    ctl: float
    atl: float
    tsb: float


def activity_load(activity: Activity, threshold_speed: float = DEFAULT_THRESHOLD_SPEED_MS) -> float:
    """Training load for a single activity."""
    if activity.relative_effort:
        return float(activity.relative_effort)

    if activity.moving_time_s <= 0 or activity.distance_m <= 0:
        return 0.0

    speed = activity.avg_speed or (activity.distance_m / activity.moving_time_s)
    if speed <= 0 or threshold_speed <= 0:
        return 0.0

    intensity = speed / threshold_speed
    return (activity.moving_time_s / 3600.0) * (intensity**2) * 100.0


def daily_loads(
    db: Session, athlete_id: int, threshold_speed: float = DEFAULT_THRESHOLD_SPEED_MS
) -> dict[date, float]:
    activities = list(db.scalars(runs_query(athlete_id)).all())
    out: dict[date, float] = {}
    for a in activities:
        day = a.start_local.date()
        out[day] = out.get(day, 0.0) + activity_load(a, threshold_speed)
    return out


def build_series(
    loads: dict[date, float], start: date | None = None, end: date | None = None
) -> list[LoadDay]:
    """Expand sparse daily loads into a continuous CTL/ATL/TSB series.

    Rest days must be materialised as zero-load days or the exponential
    averages decay far too slowly — which is exactly how a plan ends up
    believing an athlete who missed eleven days is still fit.
    """
    if not loads and (start is None or end is None):
        return []

    start = start or min(loads)
    end = end or max(loads)

    series: list[LoadDay] = []
    ctl = atl = 0.0
    day = start
    while day <= end:
        load = loads.get(day, 0.0)
        prev_ctl, prev_atl = ctl, atl
        ctl += (load - ctl) / CTL_DAYS
        atl += (load - atl) / ATL_DAYS
        series.append(
            LoadDay(
                date=day,
                load=round(load, 2),
                ctl=round(ctl, 2),
                atl=round(atl, 2),
                tsb=round(prev_ctl - prev_atl, 2),
            )
        )
        day += timedelta(days=1)
    return series


def series(
    db: Session,
    athlete_id: int,
    *,
    start: date | None = None,
    end: date | None = None,
    threshold_speed: float = DEFAULT_THRESHOLD_SPEED_MS,
) -> list[LoadDay]:
    return build_series(daily_loads(db, athlete_id, threshold_speed), start, end)


def current(db: Session, athlete_id: int, end: date | None = None) -> LoadDay | None:
    s = series(db, athlete_id, end=end)
    return s[-1] if s else None


def has_recent_heartrate(db: Session, athlete_id: int, days: int = 30) -> bool:
    """Whether any analysable run in the window recorded heart rate.

    Derived, never hardcoded: the original spec pinned this to "August", but
    the gap in fact reaches back further, and it will need to flip the moment
    the watch starts recording again.
    """
    cutoff = date.today() - timedelta(days=days)
    stmt = runs_query(athlete_id, start=cutoff).with_only_columns(Activity.has_heartrate)
    return any(db.scalars(stmt).all())


def last_heartrate_date(db: Session, athlete_id: int) -> date | None:
    stmt = (
        select(Activity.start_local)
        .where(Activity.id.in_(select(runs_query(athlete_id).subquery().c.id)))
        .where(Activity.has_heartrate.is_(True))
        .order_by(Activity.start_local.desc())
        .limit(1)
    )
    found = db.scalar(stmt)
    return found.date() if found else None
