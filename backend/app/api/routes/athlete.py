from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import current_athlete
from app.models import Athlete

router = APIRouter(prefix="/api/athlete", tags=["athlete"])


class AthleteOut(BaseModel):
    id: int
    strava_id: int
    name: str | None
    measurement_pref: str
    goal_race_distance_m: float | None
    goal_time_s: int | None
    goal_race_date: date | None
    max_sessions_per_week: int | None


@router.get("", response_model=AthleteOut)
def get_athlete(athlete: Athlete = Depends(current_athlete)) -> Athlete:
    return athlete
