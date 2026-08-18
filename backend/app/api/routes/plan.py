from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import current_athlete
from app.db import get_db
from app.models import Athlete, Plan
from app.planner import adapt, service
from app.planner.engine import PlanTooShort
from app.schemas.responses import fmt_duration

router = APIRouter(prefix="/api/plan", tags=["plan"])

VALID_STATUSES = {"planned", "done", "missed", "moved"}


class PlanSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_no: int
    day_of_week: int
    date: date
    session_type: str
    target_distance_m: float | None
    target_pace_low: float | None
    target_pace_high: float | None
    structure: dict | None
    notes: str | None
    status: str
    matched_activity_id: int | None


class PlanWeekOut(BaseModel):
    week_no: int
    start: date
    end: date
    #: Prescribed running for the week, excluding the race itself — the race is
    #: the goal, not training volume, and folding it in makes race week look
    #: like the biggest week of the block.
    target_km: float
    race_km: float
    long_run_m: float
    sessions: list[PlanSessionOut]


class PlanOut(BaseModel):
    id: int
    athlete_id: int
    goal_time_s: int
    goal_time_display: str | None
    race_date: date
    start_date: date
    weeks: int
    engine_version: str
    meta: dict | None
    weeks_detail: list[PlanWeekOut]
    compliance: dict[str, int]


class StatusPatch(BaseModel):
    status: str


def _to_weeks(sessions: list, plan_start: date) -> list[PlanWeekOut]:
    by_week: dict[int, list] = {}
    for s in sessions:
        by_week.setdefault(s.week_no, []).append(s)

    out: list[PlanWeekOut] = []
    for week_no in sorted(by_week):
        group = sorted(by_week[week_no], key=lambda s: s.date)
        # Week boundaries come from the plan's Monday grid, not from whichever
        # day the first session happens to fall on.
        start = plan_start + timedelta(weeks=week_no - 1)
        training = [s for s in group if s.session_type != "race"]
        race = [s for s in group if s.session_type == "race"]
        longs = [s.target_distance_m or 0 for s in group if s.session_type == "long"]

        out.append(
            PlanWeekOut(
                week_no=week_no,
                start=start,
                end=start + timedelta(days=6),
                target_km=round(sum((s.target_distance_m or 0) for s in training) / 1000, 1),
                race_km=round(sum((s.target_distance_m or 0) for s in race) / 1000, 1),
                long_run_m=max(longs) if longs else 0.0,
                sessions=[PlanSessionOut.model_validate(s) for s in group],
            )
        )
    return out


def _render(db: Session, plan: Plan) -> PlanOut:
    sessions = service.sessions_for(db, plan.id)
    compliance = {"planned": 0, "done": 0, "missed": 0, "moved": 0}
    for s in sessions:
        compliance[s.status] = compliance.get(s.status, 0) + 1

    return PlanOut(
        id=plan.id,
        athlete_id=plan.athlete_id,
        goal_time_s=plan.goal_time_s,
        goal_time_display=fmt_duration(plan.goal_time_s),
        race_date=plan.race_date,
        start_date=plan.start_date,
        weeks=plan.weeks,
        engine_version=plan.engine_version,
        meta=plan.meta,
        weeks_detail=_to_weeks(sessions, plan.start_date),
        compliance=compliance,
    )


@router.post("/generate", response_model=PlanOut)
def generate_plan(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> PlanOut:
    try:
        plan, _ = service.build_and_save(db, athlete)
    except PlanTooShort as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    service.reconcile(db, athlete, plan)
    return _render(db, plan)


@router.get("/current", response_model=PlanOut)
def get_current(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> PlanOut:
    plan = service.current_plan(db, athlete.id)
    if plan is None:
        raise HTTPException(
            status_code=404, detail="No plan yet. POST /api/plan/generate to create one."
        )
    return _render(db, plan)


@router.post("/reconcile", response_model=PlanOut)
def reconcile_plan(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> PlanOut:
    """Re-match completed runs onto prescribed sessions. Idempotent."""
    plan = service.current_plan(db, athlete.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No plan to reconcile")
    service.reconcile(db, athlete, plan)
    return _render(db, plan)


@router.get("/{plan_id}/week/{week_no}", response_model=PlanWeekOut)
def get_week(
    plan_id: int,
    week_no: int,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> PlanWeekOut:
    plan = db.get(Plan, plan_id)
    if plan is None or plan.athlete_id != athlete.id:
        raise HTTPException(status_code=404, detail="Plan not found")

    sessions = service.sessions_for(db, plan_id, week_no)
    if not sessions:
        raise HTTPException(status_code=404, detail=f"Week {week_no} not in this plan")
    return _to_weeks(sessions, plan.start_date)[0]


@router.patch("/session/{session_id}", response_model=PlanSessionOut)
def patch_session(
    session_id: int,
    patch: StatusPatch,
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> PlanSessionOut:
    from app.models import PlanSession

    session = db.get(PlanSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    plan = db.get(Plan, session.plan_id)
    if plan is None or plan.athlete_id != athlete.id:
        raise HTTPException(status_code=404, detail="Session not found")

    if patch.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(VALID_STATUSES)}",
        )

    session.status = patch.status
    db.commit()
    return PlanSessionOut.model_validate(session)


class AdaptationOut(BaseModel):
    rule: str
    severity: str
    action: str
    message: str
    data: dict


@router.get("/adaptations", response_model=list[AdaptationOut])
def adaptations(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> list[AdaptationOut]:
    """Deterministic re-plan signals. Same history, same answers, every time."""
    plan = service.current_plan(db, athlete.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No plan to evaluate")

    service.reconcile(db, athlete, plan)
    return [AdaptationOut(**vars(a)) for a in adapt.evaluate(db, athlete, plan)]


@router.get("/digest", response_model=dict)
def digest(
    athlete: Athlete = Depends(current_athlete), db: Session = Depends(get_db)
) -> dict:
    """This week in review: prescribed against actual, plus any adaptations."""
    plan = service.current_plan(db, athlete.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No plan to summarise")

    service.reconcile(db, athlete, plan)
    return adapt.digest(db, athlete, plan)
