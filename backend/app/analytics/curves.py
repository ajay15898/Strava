"""Pace-at-distance curve, built from Strava's own best-effort records.

Strava computes best efforts per activity and returns them on the detail
payload, so the curve needs no stream data at all. That is what moves this out
of the streams milestone: `best_effort` rows are an ingest-time artefact.

`PacePoint.is_maximal` is a *display hint only*, and a weak one: it marks
efforts whose parent activity was run at close to the effort's own pace. That
works for a short effort inside a long run, but it is meaningless when the
effort spans nearly the whole activity — a 15 K effort inside a 15.01 km run
trivially matches the run's pace whether or not it was hard. Deciding maximality
honestly needs heart rate, which this athlete's recent activities lack. The
predictor therefore ignores this flag and ranks efforts by implied performance
instead; see `predict.choose_reference`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.base import runs_query
from app.models import Activity, BestEffort

# Strava names best efforts differently across the v3 API and some wrappers;
# both spellings map to the same canonical distance.
EFFORT_DISTANCES_M: dict[str, float] = {
    "400m": 400.0,
    "fastest400": 400.0,
    "1/2 mile": 804.67,
    "fastesthalfmile": 804.67,
    "1k": 1000.0,
    "fastest1k": 1000.0,
    "1 mile": 1609.34,
    "fastestmile": 1609.34,
    "2 mile": 3218.69,
    "fastest2mile": 3218.69,
    "5k": 5000.0,
    "fastest5k": 5000.0,
    "10k": 10000.0,
    "fastest10k": 10000.0,
    "15k": 15000.0,
    "fastest15k": 15000.0,
    "10 mile": 16093.4,
    "fastest10mile": 16093.4,
    "20k": 20000.0,
    "fastest20k": 20000.0,
    "half-marathon": 21097.5,
    "fastesthalfmarathon": 21097.5,
    "30k": 30000.0,
    "fastest30k": 30000.0,
    "marathon": 42195.0,
    "fastestmarathon": 42195.0,
}

# Display hint: the parent activity's average pace is within this factor of the
# effort's own pace. Unreliable for efforts spanning most of the activity.
MAXIMAL_PACE_RATIO = 1.15


def canonical_distance(effort_type: str) -> float | None:
    return EFFORT_DISTANCES_M.get(effort_type.strip().lower())


@dataclass
class PacePoint:
    distance_m: float
    duration_s: int
    activity_id: int
    activity_date: date
    effort_type: str
    is_maximal: bool

    @property
    def pace_s_per_km(self) -> float:
        return self.duration_s / (self.distance_m / 1000.0)


def _points_from_rows(rows) -> list[PacePoint]:
    points: list[PacePoint] = []
    for effort, activity in rows:
        distance = canonical_distance(effort.effort_type) or effort.distance_m
        if not distance or effort.duration_s <= 0:
            continue
        effort_pace = effort.duration_s / (distance / 1000.0)
        activity_pace = activity.pace_s_per_km
        is_maximal = (
            activity_pace is not None and activity_pace <= effort_pace * MAXIMAL_PACE_RATIO
        )
        points.append(
            PacePoint(
                distance_m=distance,
                duration_s=effort.duration_s,
                activity_id=activity.id,
                activity_date=activity.start_local.date(),
                effort_type=effort.effort_type,
                is_maximal=is_maximal,
            )
        )
    return points


def pace_points(db: Session, athlete_id: int, since: date | None = None) -> list[PacePoint]:
    valid_ids = select(runs_query(athlete_id, start=since).subquery().c.id)
    rows = db.execute(
        select(BestEffort, Activity)
        .join(Activity, BestEffort.activity_id == Activity.id)
        .where(Activity.id.in_(valid_ids))
    ).all()
    return _points_from_rows(rows)


def best_at_distance(
    points: list[PacePoint], *, maximal_only: bool = False
) -> dict[float, PacePoint]:
    """Fastest recorded effort at each canonical distance."""
    best: dict[float, PacePoint] = {}
    for p in points:
        if maximal_only and not p.is_maximal:
            continue
        current = best.get(p.distance_m)
        if current is None or p.duration_s < current.duration_s:
            best[p.distance_m] = p
    return best


def curve(db: Session, athlete_id: int, since: date | None = None) -> list[PacePoint]:
    """The pace-at-distance curve: best effort per distance, ascending."""
    points = pace_points(db, athlete_id, since)
    return sorted(best_at_distance(points).values(), key=lambda p: p.distance_m)
