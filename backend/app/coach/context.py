"""Builds the CoachContext.

Everything the coach is allowed to say is computed here, before any model call.
The model receives this object and may paraphrase, prioritise and explain it —
it may not produce a number that is not in here, and `verify.py` enforces that
mechanically rather than by asking the prompt nicely.

Which means this module has a second job beyond assembling data: anything
missing from the context is something the coach *cannot discuss*. If it should
be able to answer a question, the number has to be here.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from sqlalchemy.orm import Session

from app.analytics import consistency, load as load_mod, predict
from app.analytics.base import valid_runs
from app.analytics.curves import curve
from app.models import Athlete
from app.planner import adapt, service as plan_service


def build(db: Session, athlete: Athlete, *, today: date | None = None) -> dict:
    today = today or date.today()

    runs = valid_runs(db, athlete.id)
    if not runs:
        return {"athlete": _athlete_block(athlete, today), "flags": ["no_activity_data"]}

    window_start = runs[0].start_local.date()
    window_end = runs[-1].start_local.date()
    report = consistency.build_report(runs, window_start, window_end)

    context: dict = {
        "generated_for_date": today.isoformat(),
        "athlete": _athlete_block(athlete, today),
        "fitness": _fitness_block(db, athlete, runs, report, today),
        "recent_activities": _recent_activities(runs),
        "compliance": _compliance_block(report),
        "flags": [],
    }

    prediction = predict.predict(db, athlete.id, athlete.goal_race_distance_m or 21097.5, today=today)
    if prediction is not None:
        context["prediction"] = _prediction_block(prediction)
        if athlete.goal_time_s:
            feasibility = predict.assess(
                prediction, athlete.goal_time_s, report.km_per_week_4wk
            )
            context["feasibility"] = asdict(feasibility)

    plan = plan_service.current_plan(db, athlete.id)
    if plan is not None:
        context["plan"] = _plan_block(db, athlete, plan, today)
        context["adaptations"] = [
            {"rule": a.rule, "severity": a.severity, "action": a.action, "message": a.message}
            for a in adapt.evaluate(db, athlete, plan, today=today)
        ]

    context["flags"] = _flags(db, athlete, report, context)
    return context


def _athlete_block(athlete: Athlete, today: date) -> dict:
    weeks_out = None
    if athlete.goal_race_date:
        weeks_out = round((athlete.goal_race_date - today).days / 7, 1)

    return {
        "name": athlete.name,
        "goal_race_distance_m": athlete.goal_race_distance_m,
        "goal_time_s": athlete.goal_time_s,
        "goal_race_date": athlete.goal_race_date.isoformat() if athlete.goal_race_date else None,
        "weeks_out": weeks_out,
        "max_sessions_per_week": athlete.max_sessions_per_week,
    }


def _fitness_block(db, athlete, runs, report, today) -> dict:
    current = load_mod.current(db, athlete.id, end=today)
    points = curve(db, athlete.id)
    best = {p.effort_type: p.duration_s for p in points}

    return {
        "total_km": report.total_km,
        "total_run_days": report.total_run_days,
        "weekly_km_2wk": report.km_per_week_2wk,
        "weekly_km_4wk": report.km_per_week_4wk,
        "weekly_km_overall": report.km_per_week_overall,
        "longest_run_m": round(max(r.distance_m for r in runs), 1),
        "best_efforts_s": best,
        "ctl": current.ctl if current else None,
        "atl": current.atl if current else None,
        "tsb": current.tsb if current else None,
        "has_recent_heartrate": load_mod.has_recent_heartrate(db, athlete.id),
        "window_start": report.window_start.isoformat(),
        "window_end": report.window_end.isoformat(),
    }


def _recent_activities(runs, limit: int = 10) -> list[dict]:
    return [
        {
            "date": r.start_local.date().isoformat(),
            "name": r.name,
            "distance_m": round(r.distance_m, 1),
            "moving_time_s": r.moving_time_s,
            "pace_s_per_km": round(r.moving_time_s / (r.distance_m / 1000), 1),
            "avg_hr": r.avg_hr,
        }
        for r in sorted(runs, key=lambda a: a.start_local, reverse=True)[:limit]
    ]


def _compliance_block(report) -> dict:
    return {
        "weekly_km_last_8": [round(w.km, 1) for w in report.weeks],
        "run_days_last_8": [w.run_days for w in report.weeks],
        "longest_gap_days": report.longest_gap_days,
        "gaps": [
            {"start": g.start.isoformat(), "end": g.end.isoformat(), "days": g.days}
            for g in report.gaps
        ],
    }


def _prediction_block(p) -> dict:
    return {
        "predicted_time_s": p.predicted_time_s,
        "predicted_pace_s_per_km": round(p.predicted_pace_s_per_km, 1),
        "riegel_s": p.riegel_s,
        "cameron_s": p.cameron_s,
        "blended_s": p.blended_s,
        "durability_ratio": p.durability_ratio,
        "durability_penalty_pct": p.durability_penalty_pct,
        "reference_effort_type": p.reference_effort_type,
        "reference_duration_s": p.reference_duration_s,
        "reference_date": p.reference_date.isoformat(),
        "longest_run_m": round(p.longest_run_m, 1),
    }


def _plan_block(db, athlete, plan, today: date) -> dict:
    sessions = plan_service.sessions_for(db, plan.id)
    week_no = None
    if sessions:
        current_week = [s for s in sessions if s.date >= today]
        week_no = current_week[0].week_no if current_week else sessions[-1].week_no

    this_week = [s for s in sessions if s.week_no == week_no]
    counts: dict[str, int] = {}
    for s in sessions:
        counts[s.status] = counts.get(s.status, 0) + 1

    meta = plan.meta or {}
    return {
        "plan_id": plan.id,
        "engine_version": plan.engine_version,
        "start_date": plan.start_date.isoformat(),
        "race_date": plan.race_date.isoformat(),
        "weeks": plan.weeks,
        "current_week_no": week_no,
        "peak_weekly_km": meta.get("peak_weekly_km"),
        "peak_long_run_m": meta.get("peak_long_run_m"),
        "total_km": meta.get("total_km"),
        "warnings": meta.get("warnings", []),
        "paces": meta.get("paces", {}),
        "session_status_counts": counts,
        "this_week": [
            {
                "date": s.date.isoformat(),
                "session_type": s.session_type,
                "target_distance_m": s.target_distance_m,
                "target_pace_low": s.target_pace_low,
                "target_pace_high": s.target_pace_high,
                "status": s.status,
                "notes": s.notes,
            }
            for s in this_week
        ],
    }


def _flags(db, athlete, report, context: dict) -> list[str]:
    flags: list[str] = []

    fitness = context.get("fitness", {})
    if not fitness.get("has_recent_heartrate"):
        flags.append("no_heart_rate_data")
    if report.km_per_week_4wk < 25:
        flags.append("volume_below_target")
    if report.longest_gap_days >= 7:
        flags.append("consistency_gaps")

    prediction = context.get("prediction")
    if prediction and prediction["durability_penalty_pct"] > 0:
        flags.append("durability_penalty_applied")

    feasibility = context.get("feasibility")
    if feasibility and feasibility["verdict"] != "on_track":
        flags.append(f"feasibility_{feasibility['verdict']}")

    if not context.get("plan"):
        flags.append("no_plan_generated")

    return flags
