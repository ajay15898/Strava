"""Persisting generated plans, and matching real activities against them.

Plans are versioned rather than mutated: regenerating supersedes the previous
plan and leaves it queryable. A plan that has been trained against is evidence
of what was prescribed at the time, and overwriting it would destroy the only
record of why a week looked the way it did.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import consistency, predict
from app.analytics.base import valid_runs
from app.analytics.curves import pace_points
from app.models import Activity, Athlete, Plan, PlanSession
from app.planner.engine import (
    ENGINE_VERSION,
    FitnessSnapshot,
    GeneratedPlan,
    PlanTooShort,
    generate,
)
from app.planner.phases import pattern_from_config

# A completed run counts as a prescribed session if it lands within this many
# days of it. One day either side absorbs "I did Sunday's long run on Monday"
# without letting an unrelated midweek run claim the slot.
MATCH_WINDOW_DAYS = 1

# Distance tolerance for calling a session done as prescribed.
MATCH_DISTANCE_TOLERANCE = 0.20


def snapshot_fitness(db: Session, athlete: Athlete, today: date) -> FitnessSnapshot:
    """Everything the engine needs about current form, read from the database."""
    runs = valid_runs(db, athlete.id)
    if not runs:
        raise PlanTooShort("No runs on record — nothing to plan from.")

    window_end = runs[-1].start_local.date()
    report = consistency.build_report(runs, runs[0].start_local.date(), window_end)

    points = pace_points(db, athlete.id)
    reference = predict.choose_reference(points, today, athlete.goal_race_distance_m or 21097.5)
    if reference is None:
        raise PlanTooShort(
            "No best-effort data to derive paces from. Run a backfill first."
        )

    return FitnessSnapshot(
        reference_distance_m=reference.distance_m,
        reference_duration_s=reference.duration_s,
        longest_run_m=max(r.distance_m for r in runs),
        weekly_km_2wk=report.km_per_week_2wk,
        weekly_km_4wk=report.km_per_week_4wk,
    )


def _meta(plan: GeneratedPlan) -> dict:
    table = plan.pace_table
    return {
        "compressed": plan.compressed,
        "start_date": plan.start_date.isoformat(),
        "warnings": plan.warnings,
        "peak_weekly_km": plan.peak_weekly_km,
        "peak_long_run_m": plan.peak_long_run_m,
        "total_km": round(plan.total_km, 1),
        "reference": {
            "distance_m": table.reference_distance_m,
            "duration_s": table.reference_duration_s,
        },
        "paces": {
            name: {"low": round(table.band(name).low, 1), "high": round(table.band(name).high, 1)}
            for name in ("recovery", "easy", "long", "goal", "threshold", "interval", "strides")
        },
    }


def save(db: Session, athlete: Athlete, generated: GeneratedPlan) -> Plan:
    """Persist a generated plan, superseding whatever it replaces."""
    previous = current_plan(db, athlete.id)

    plan = Plan(
        athlete_id=athlete.id,
        goal_time_s=generated.goal_time_s,
        race_date=generated.race_date,
        start_date=generated.start_date,
        weeks=generated.weeks,
        engine_version=generated.engine_version,
        meta=_meta(generated),
    )
    db.add(plan)
    db.flush()

    for week in generated.week_plans:
        for session in week.sessions:
            db.add(
                PlanSession(
                    plan_id=plan.id,
                    week_no=session.week_no,
                    day_of_week=session.day_of_week,
                    date=session.date,
                    session_type=session.session_type,
                    target_distance_m=session.target_distance_m,
                    target_pace_low=session.target_pace_low,
                    target_pace_high=session.target_pace_high,
                    structure=session.structure,
                    # The label is generation-time only; fold it in so a
                    # standing commitment stays identifiable on the plan.
                    notes=(
                        f"{session.label} — {session.notes}"
                        if session.label
                        else session.notes
                    ),
                    status="planned",
                )
            )

    if previous is not None:
        previous.superseded_by = plan.id

    db.commit()
    return plan


def build_and_save(
    db: Session, athlete: Athlete, *, today: date | None = None
) -> tuple[Plan, GeneratedPlan]:
    today = today or date.today()

    if not athlete.goal_race_date or not athlete.goal_time_s or not athlete.goal_race_distance_m:
        raise PlanTooShort("Athlete has no goal race set.")

    prefs = athlete.preferences or {}
    fitness = snapshot_fitness(db, athlete, today)
    generated = generate(
        fitness=fitness,
        goal_distance_m=athlete.goal_race_distance_m,
        goal_time_s=athlete.goal_time_s,
        race_date=athlete.goal_race_date,
        today=today,
        sessions_per_week=athlete.max_sessions_per_week or 4,
        pattern=pattern_from_config(prefs.get("week_pattern")),
        # Anchor to the Monday just gone rather than the next one. With a
        # compressed block a whole week of runway is worth more than a tidy
        # start date, and any session already past is simply reconciled.
        start_this_week=bool(prefs.get("start_this_week", True)),
    )
    return save(db, athlete, generated), generated


def current_plan(db: Session, athlete_id: int) -> Plan | None:
    """The live plan: the most recent one nothing has superseded."""
    return db.scalar(
        select(Plan)
        .where(Plan.athlete_id == athlete_id, Plan.superseded_by.is_(None))
        .order_by(Plan.generated_at.desc())
        .limit(1)
    )


def sessions_for(db: Session, plan_id: int, week_no: int | None = None) -> list[PlanSession]:
    stmt = select(PlanSession).where(PlanSession.plan_id == plan_id)
    if week_no is not None:
        stmt = stmt.where(PlanSession.week_no == week_no)
    return list(db.scalars(stmt.order_by(PlanSession.date)).all())


def reconcile(db: Session, athlete: Athlete, plan: Plan) -> dict[str, int]:
    """Match completed runs onto prescribed sessions.

    Deterministic and re-runnable: it never invents a session and never marks
    a future session missed, so running it twice changes nothing.
    """
    sessions = sessions_for(db, plan.id)
    if not sessions:
        return {"done": 0, "missed": 0, "planned": 0}

    runs = valid_runs(db, athlete.id, plan.start_date, plan.race_date)
    unclaimed = {r.id: r for r in runs}
    today = date.today()

    counts = {"done": 0, "missed": 0, "planned": 0}

    for session in sorted(sessions, key=lambda s: s.date):
        match = _best_match(session, unclaimed)
        if match is not None:
            unclaimed.pop(match.id, None)
            session.status = "done"
            session.matched_activity_id = match.id
            counts["done"] += 1
        elif session.date < today:
            session.status = "missed"
            session.matched_activity_id = None
            counts["missed"] += 1
        else:
            session.status = "planned"
            counts["planned"] += 1

    db.commit()
    return counts


def _best_match(session: PlanSession, candidates: dict[int, Activity]) -> Activity | None:
    window = timedelta(days=MATCH_WINDOW_DAYS)
    best: Activity | None = None
    best_gap: float | None = None

    for activity in candidates.values():
        day = activity.start_local.date()
        if abs(day - session.date) > window:
            continue
        if session.target_distance_m:
            ratio = activity.distance_m / session.target_distance_m
            if not (1 - MATCH_DISTANCE_TOLERANCE <= ratio <= 1 + MATCH_DISTANCE_TOLERANCE):
                continue
        gap = abs((day - session.date).days)
        if best_gap is None or gap < best_gap:
            best, best_gap = activity, gap

    return best


def as_dict(generated: GeneratedPlan) -> dict:
    """Plain-dict view of a freshly generated plan, for the API layer."""
    payload = asdict(generated)
    table = generated.pace_table
    payload["pace_table"] = {
        name: {
            "low": round(table.band(name).low, 1),
            "high": round(table.band(name).high, 1),
            "display": table.band(name).format(),
        }
        for name in ("recovery", "easy", "long", "goal", "threshold", "interval", "strides")
    }
    return payload
