from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analytics import consistency, load, predict
from app.analytics.base import valid_runs
from app.analytics.curves import curve
from app.api.deps import current_athlete
from app.constants import HALF_MARATHON_M
from app.db import get_db
from app.models import Athlete
from app.schemas.responses import (
    FeasibilityOut,
    GapOut,
    LoadDayOut,
    MonthOut,
    PacePointOut,
    PredictionOut,
    SummaryOut,
    WeekOut,
    fmt_duration,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=SummaryOut)
def summary(
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> SummaryOut:
    runs = valid_runs(db, athlete.id, date_from, date_to)
    if not runs:
        raise HTTPException(status_code=404, detail="No runs in range")

    start = date_from or runs[0].start_local.date()
    end = date_to or runs[-1].start_local.date()
    report = consistency.build_report(runs, start, end)

    return SummaryOut(
        window_start=report.window_start,
        window_end=report.window_end,
        total_km=report.total_km,
        total_run_days=report.total_run_days,
        km_per_week_overall=report.km_per_week_overall,
        km_per_week_2wk=report.km_per_week_2wk,
        km_per_week_4wk=report.km_per_week_4wk,
        longest_gap_days=report.longest_gap_days,
        gaps=[GapOut(start=g.start, end=g.end, days=g.days) for g in report.gaps],
        weeks=[
            WeekOut(start=w.start, end=w.end, km=round(w.km, 2), run_days=w.run_days)
            for w in report.weeks
        ],
        months=[
            MonthOut(
                year=m.year,
                month=m.month,
                km=round(m.km, 2),
                run_days=m.run_days,
                span_days=m.span_days,
                km_per_week=round(m.km_per_week, 2),
            )
            for m in report.months
        ],
        has_recent_heartrate=load.has_recent_heartrate(db, athlete.id),
        last_heartrate_date=load.last_heartrate_date(db, athlete.id),
    )


@router.get("/load", response_model=list[LoadDayOut])
def load_series(
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
) -> list[LoadDayOut]:
    return [
        LoadDayOut(date=d.date, load=d.load, ctl=d.ctl, atl=d.atl, tsb=d.tsb)
        for d in load.series(db, athlete.id, start=date_from, end=date_to)
    ]


@router.get("/curve", response_model=list[PacePointOut])
def pace_curve(
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
    since: date | None = Query(default=None),
) -> list[PacePointOut]:
    return [
        PacePointOut(
            distance_m=p.distance_m,
            duration_s=p.duration_s,
            duration_display=fmt_duration(p.duration_s),
            pace_s_per_km=round(p.pace_s_per_km, 1),
            activity_id=p.activity_id,
            activity_date=p.activity_date,
            effort_type=p.effort_type,
            is_maximal=p.is_maximal,
        )
        for p in curve(db, athlete.id, since)
    ]


@router.get("/prediction", response_model=PredictionOut)
def prediction(
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
    distance: float = Query(default=HALF_MARATHON_M),
) -> PredictionOut:
    p = predict.predict(db, athlete.id, distance)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail="No best-effort data. Run POST /api/sync/backfill first.",
        )
    return PredictionOut(
        target_distance_m=p.target_distance_m,
        reference_distance_m=p.reference_distance_m,
        reference_duration_s=p.reference_duration_s,
        reference_duration_display=fmt_duration(p.reference_duration_s),
        reference_date=p.reference_date,
        reference_effort_type=p.reference_effort_type,
        used_maximal_reference=p.used_maximal_reference,
        riegel_s=p.riegel_s,
        cameron_s=p.cameron_s,
        blended_s=p.blended_s,
        durability_ratio=p.durability_ratio,
        durability_penalty_pct=p.durability_penalty_pct,
        longest_run_m=round(p.longest_run_m, 1),
        predicted_time_s=p.predicted_time_s,
        predicted_time_display=fmt_duration(p.predicted_time_s),
        predicted_pace_s_per_km=round(p.predicted_pace_s_per_km, 1),
        notes=p.notes,
    )


@router.get("/feasibility", response_model=FeasibilityOut)
def feasibility(
    athlete: Athlete = Depends(current_athlete),
    db: Session = Depends(get_db),
) -> FeasibilityOut:
    if not athlete.goal_time_s or not athlete.goal_race_distance_m:
        raise HTTPException(status_code=400, detail="Athlete has no goal set")

    p = predict.predict(db, athlete.id, athlete.goal_race_distance_m)
    if p is None:
        raise HTTPException(status_code=404, detail="No best-effort data available")

    runs = valid_runs(db, athlete.id)
    end = runs[-1].start_local.date() if runs else date.today()
    weekly = consistency.window_km(runs, end, 28) / 4

    f = predict.assess(p, athlete.goal_time_s, weekly)
    return FeasibilityOut(
        verdict=f.verdict,
        predicted_time_s=f.predicted_time_s,
        predicted_time_display=fmt_duration(f.predicted_time_s),
        required_weekly_peak_km=f.required_weekly_peak_km,
        current_weekly_km=f.current_weekly_km,
        limiting_factor=f.limiting_factor,
    )
