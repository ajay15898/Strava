from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_athlete
from app.db import get_db
from app.analytics import streams as streams_mod
from app.models import Activity, ActivitySplit, ActivityStream, Athlete
from app.strava import sync as sync_mod
from app.schemas.responses import ActivityOut

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("", response_model=list[ActivityOut])
def list_activities(
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    sport_type: str | None = Query(default=None, alias="type"),
    include_duplicates: bool = Query(default=False),
    limit: int = Query(default=200, le=1000),
) -> list[Activity]:
    stmt = select(Activity).where(Activity.athlete_id == athlete.id)

    if not include_duplicates:
        stmt = stmt.where(Activity.is_duplicate.is_(False))
    if sport_type:
        stmt = stmt.where(Activity.sport_type == sport_type)
    if date_from:
        stmt = stmt.where(Activity.start_local >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Activity.start_local <= datetime.combine(date_to, datetime.max.time()))

    stmt = stmt.order_by(Activity.start_local.desc()).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/{activity_id}", response_model=ActivityOut)
def get_activity(
    activity_id: int,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> Activity:
    activity = db.scalar(
        select(Activity).where(
            Activity.id == activity_id, Activity.athlete_id == athlete.id
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.get("/{activity_id}/streams")
def get_streams(
    activity_id: int,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    activity = db.scalar(
        select(Activity).where(
            Activity.id == activity_id, Activity.athlete_id == athlete.id
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    streams = db.scalars(
        select(ActivityStream).where(ActivityStream.activity_id == activity_id)
    ).all()
    return {s.type: s.data for s in streams}


def _owned(db: Session, athlete: Athlete, activity_id: int) -> Activity:
    activity = db.scalar(
        select(Activity).where(
            Activity.id == activity_id, Activity.athlete_id == athlete.id
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.post("/{activity_id}/streams/fetch")
def fetch_streams(
    activity_id: int,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Pull this activity's streams from Strava on demand.

    Streams are the expensive call, so nothing fetches them speculatively —
    they arrive when someone actually opens the run.
    """
    activity = _owned(db, athlete, activity_id)
    if sync_mod.has_streams(db, activity.id):
        return {"status": "already_present"}
    stored = sync_mod.fetch_streams(db, athlete, activity)
    return {"status": "fetched" if stored else "unavailable", "streams": stored}


@router.get("/{activity_id}/splits")
def get_splits(
    activity_id: int,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    activity = _owned(db, athlete, activity_id)
    rows = db.scalars(
        select(ActivitySplit)
        .where(ActivitySplit.activity_id == activity.id)
        .order_by(ActivitySplit.split_index)
    ).all()
    return [
        {
            "split_index": r.split_index,
            "distance_m": r.distance_m,
            "moving_time_s": r.moving_time_s,
            "elapsed_time_s": r.elapsed_time_s,
            "pace_s_per_km": round(r.pace_s_per_km, 1) if r.pace_s_per_km else None,
            "elevation_diff_m": r.elevation_diff_m,
            "avg_hr": r.avg_hr,
        }
        for r in rows
    ]


@router.get("/{activity_id}/analysis")
def get_analysis(
    activity_id: int,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Aerobic decoupling and split fade for one run."""
    activity = _owned(db, athlete, activity_id)

    stored = {
        s.type: (s.data or {}).get("data", [])
        for s in db.scalars(
            select(ActivityStream).where(ActivityStream.activity_id == activity.id)
        ).all()
    }

    decoup = streams_mod.decoupling(
        heart_rate=stored.get("heartrate"),
        watts=stored.get("watts"),
        velocity=stored.get("velocity_smooth"),
        moving=stored.get("moving"),
    )

    splits = db.scalars(
        select(ActivitySplit)
        .where(ActivitySplit.activity_id == activity.id)
        .order_by(ActivitySplit.split_index)
    ).all()
    # Whole kilometres only — a trailing 200 m "split" is noise.
    whole = [s.pace_s_per_km for s in splits if s.distance_m >= 950 and s.pace_s_per_km]
    fade = streams_mod.split_fade(whole)

    return {
        "activity_id": activity.id,
        "has_streams": bool(stored),
        "available_streams": sorted(stored),
        "decoupling": {
            "pct": decoup.pct,
            "method": decoup.method,
            "is_concerning": decoup.is_concerning,
            "reason": decoup.reason,
        },
        "split_fade": {
            "first_km_pace_s": fade.first_km_pace_s,
            "last_km_pace_s": fade.last_km_pace_s,
            "fade_pct": fade.fade_pct,
            "fastest_km": fade.fastest_km,
            "slowest_km": fade.slowest_km,
            "negative_split": fade.negative_split,
        },
    }
