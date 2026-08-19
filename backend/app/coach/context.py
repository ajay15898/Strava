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


# --- display formatting ---------------------------------------------------
# The context carries human-readable values, not raw SI. Telling a model to
# "prefer readable units" does not work — gpt-oss-120b kept printing 7268 s and
# 15008.8 m no matter how the prompt was worded. Removing raw seconds and
# metres from the context makes that structurally impossible instead, which is
# the same principle as the verifier: do not ask, make it so.


def _hms(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _pace(seconds_per_km: float | None) -> str | None:
    if not seconds_per_km:
        return None
    s = int(round(seconds_per_km))
    return f"{s // 60}:{s % 60:02d}"


def _km(metres: float | None, digits: int = 2) -> float | None:
    return None if metres is None else round(metres / 1000, digits)


def _band(low: float | None, high: float | None) -> str | None:
    if not low or not high:
        return None
    return f"{_pace(low)}-{_pace(high)}"


def _humanise(value: str | None) -> str | None:
    return None if value is None else value.replace("_", " ")


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
            feasibility = asdict(
                predict.assess(prediction, athlete.goal_time_s, report.km_per_week_4wk)
            )
            # `required_weekly_peak_km` is a generic half-marathon guideline that
            # the prediction path never reads. Left under that name the model
            # presents it as a hard requirement, so it is renamed here to say
            # what it actually is.
            feasibility["typical_hm_peak_guideline_km"] = feasibility.pop(
                "required_weekly_peak_km"
            )
            feasibility["predicted_finish_time"] = _hms(
                feasibility.pop("predicted_time_s")
            )
            feasibility["limiting_factor"] = _humanise(feasibility["limiting_factor"])
            # `current_weekly_km` is fed the *four-week average*, not this
            # week's mileage. Under that name the model reasonably reported it
            # as "this week". Every mislabel found so far has traced back to an
            # ambiguous field name here rather than to model error — the
            # verifier proves a number is real, never that it means what the
            # sentence around it claims.
            feasibility["avg_km_per_week_last_4_weeks"] = feasibility.pop(
                "current_weekly_km"
            )
            context["feasibility"] = feasibility

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
        "goal_race_distance_km": _km(athlete.goal_race_distance_m, 1),
        "goal_time": _hms(athlete.goal_time_s),
        "goal_pace_per_km": _pace(
            athlete.goal_time_s / (athlete.goal_race_distance_m / 1000)
            if athlete.goal_time_s and athlete.goal_race_distance_m
            else None
        ),
        "goal_race_date": athlete.goal_race_date.isoformat() if athlete.goal_race_date else None,
        "weeks_out": weeks_out,
        "runs_per_week": athlete.max_sessions_per_week,
    }


def _fitness_block(db, athlete, runs, report, today) -> dict:
    current = load_mod.current(db, athlete.id, end=today)
    points = curve(db, athlete.id)
    best = {p.effort_type: p.duration_s for p in points}

    return {
        "total_km_all_time": report.total_km,
        "total_run_days_all_time": report.total_run_days,
        "avg_km_per_week_last_2_weeks": report.km_per_week_2wk,
        "avg_km_per_week_last_4_weeks": report.km_per_week_4wk,
        "avg_km_per_week_all_time": report.km_per_week_overall,
        "longest_run_ever_km": _km(max(r.distance_m for r in runs)),
        "best_efforts": {k: _hms(v) for k, v in best.items()},
        "ctl": current.ctl if current else None,
        "atl": current.atl if current else None,
        "tsb": current.tsb if current else None,
        "has_recent_heartrate": load_mod.has_recent_heartrate(db, athlete.id),
        "window_start": report.window_start.isoformat(),
        "window_end": report.window_end.isoformat(),
    }


#: Enough to discuss the last fortnight without spending the token budget
#: on history the athlete can already see in the activity table.
RECENT_ACTIVITY_LIMIT = 6


def _recent_activities(runs, limit: int = RECENT_ACTIVITY_LIMIT) -> list[dict]:
    return [
        {
            "date": r.start_local.date().isoformat(),
            "name": r.name,
            "distance_km": _km(r.distance_m),
            "duration": _hms(r.moving_time_s),
            "pace_per_km": _pace(r.moving_time_s / (r.distance_m / 1000)),
            "avg_hr": r.avg_hr,
        }
        for r in sorted(runs, key=lambda a: a.start_local, reverse=True)[:limit]
    ]


def _compliance_block(report) -> dict:
    return {
        "weekly_km_last_8": [round(w.km, 1) for w in report.weeks],
        "run_days_last_8": [w.run_days for w in report.weeks],
        "gap_count": len(report.gaps),
        "longest_gap_days": report.longest_gap_days,
        # Only the recent ones — older gaps are history, not decisions.
        "recent_gaps": [
            {"start": g.start.isoformat(), "end": g.end.isoformat(), "days": g.days}
            for g in report.gaps[-3:]
        ],
    }


def _prediction_block(p) -> dict:
    return {
        "predicted_finish_time": _hms(p.predicted_time_s),
        "predicted_pace_per_km": _pace(p.predicted_pace_s_per_km),
        "riegel_estimate": _hms(p.riegel_s),
        "cameron_estimate": _hms(p.cameron_s),
        "blended_before_penalty": _hms(p.blended_s),
        "durability_ratio_longest_run_over_race": p.durability_ratio,
        "durability_penalty_pct": p.durability_penalty_pct,
        "based_on_effort": p.reference_effort_type,
        "based_on_time": _hms(p.reference_duration_s),
        "based_on_date": p.reference_date.isoformat(),
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
        "peak_long_run_km": _km(meta.get("peak_long_run_m"), 1),
        "total_km": meta.get("total_km"),
        "warnings": meta.get("warnings", []),
        "prescribed_paces_per_km": {
            name: _band(v.get("low"), v.get("high"))
            for name, v in (meta.get("paces") or {}).items()
        },
        "session_status_counts": counts,
        "this_week": [
            {
                "date": s.date.isoformat(),
                "session_type": s.session_type,
                "target_distance_km": _km(s.target_distance_m, 1),
                "target_pace_per_km": _band(s.target_pace_low, s.target_pace_high),
                "status": s.status,
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
