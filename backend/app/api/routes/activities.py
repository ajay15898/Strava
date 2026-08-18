from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_athlete
from app.db import get_db
from app.models import Activity, ActivityStream, Athlete
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
