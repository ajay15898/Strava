"""Persisting generated plans, and matching real activities against them.

Plans are versioned rather than mutated: regenerating supersedes the previous
plan and leaves it queryable. A plan that has been trained against is evidence
of what was prescribed at the time, and overwriting it would destroy the only
record of why a week looked the way it did.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

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

# Matching is scoped to the plan week, not to a fixed day window. Training
# slips within a week constantly — Wednesday's threshold gets run on Friday —
# and a ±1 day window turns that into a phantom "missed" session *plus* an
# unattached run, which double-counts the disruption and misreports compliance.
# A run may not reach across a week boundary to satisfy an earlier week's
# session: that would let last week's shortfall be papered over by this week's
# work, which is exactly what the repeat-the-week rule exists to catch.
#
# Run on the prescribed day (within this many days) -> "done".
# Run elsewhere in the same week -> "moved".
MATCH_SAME_DAY_TOLERANCE_DAYS = 1

# How far a run's distance may sit from the prescription and still count as
# that session. Deliberately asymmetric: cutting a session short is the normal
# failure mode, while running far *over* usually means it was a different
# session entirely.
#
# A symmetric 25% band left a 12.1 km run unmatched against an 18.4 km long
# run, which was worse than it looks: the long-run-shortfall rule only inspects
# *matched* sessions, so the attempt vanished instead of triggering the rule
# written for exactly that case.
MATCH_UNDER_TOLERANCE = 0.40
MATCH_OVER_TOLERANCE = 0.25

# Scoring weights. Distance is the primary signal; pace separates a threshold
# run from an easy run of similar length; the day gap is the weakest, because
# *which* session was run matters more than when.
MATCH_DISTANCE_WEIGHT = 400.0
MATCH_PACE_BONUS = 150.0
MATCH_DAY_GAP_PENALTY = 30.0


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


def week_of(plan: Plan, day: date) -> int | None:
    """Which plan week a date falls in, or None if outside the plan."""
    if day < plan.start_date:
        return None
    week = (day - plan.start_date).days // 7 + 1
    return week if week <= plan.weeks else None


def match_score(session: PlanSession, activity: Activity) -> float | None:
    """How well a run fits a prescribed session. None means implausible.

    Scored rather than filtered on date, so a 7 km threshold run on Friday
    claims Wednesday's threshold slot instead of Thursday's 5 km easy one.
    """
    if not session.target_distance_m:
        return None

    ratio = activity.distance_m / session.target_distance_m
    if not (1 - MATCH_UNDER_TOLERANCE <= ratio <= 1 + MATCH_OVER_TOLERANCE):
        return None

    score = 1000.0 - abs(1 - ratio) * MATCH_DISTANCE_WEIGHT

    # Pace is what distinguishes session *type* at similar distances.
    if session.target_pace_low and session.target_pace_high and activity.distance_m > 0:
        actual = activity.moving_time_s / (activity.distance_m / 1000)
        if session.target_pace_low <= actual <= session.target_pace_high:
            score += MATCH_PACE_BONUS

    score -= abs((activity.start_local.date() - session.date).days) * MATCH_DAY_GAP_PENALTY
    return score


def reconcile(db: Session, athlete: Athlete, plan: Plan) -> dict[str, int]:
    """Match completed runs onto prescribed sessions, within each plan week.

    Deterministic and re-runnable: it never invents a session, never marks a
    future session missed, and assigns the globally best-scoring pairs first
    rather than walking sessions in date order — so one early session cannot
    greedily claim a run that fits a later one far better.
    """
    sessions = sessions_for(db, plan.id)
    if not sessions:
        return {"done": 0, "moved": 0, "missed": 0, "planned": 0, "unmatched_runs": 0}

    runs = valid_runs(db, athlete.id, plan.start_date, plan.race_date)
    today = date.today()

    # Every plausible pairing inside the same plan week, best first.
    pairs: list[tuple[float, PlanSession, Activity]] = []
    for session in sessions:
        for activity in runs:
            if week_of(plan, activity.start_local.date()) != session.week_no:
                continue
            score = match_score(session, activity)
            if score is not None:
                pairs.append((score, session, activity))

    # Ties broken on ids so the result never depends on iteration order.
    pairs.sort(key=lambda p: (-p[0], p[1].id, p[2].id))

    claimed_sessions: set[int] = set()
    claimed_runs: set[int] = set()
    assignment: dict[int, Activity] = {}

    for _, session, activity in pairs:
        if session.id in claimed_sessions or activity.id in claimed_runs:
            continue
        claimed_sessions.add(session.id)
        claimed_runs.add(activity.id)
        assignment[session.id] = activity

    counts = {"done": 0, "moved": 0, "missed": 0, "planned": 0, "unmatched_runs": 0}

    for session in sessions:
        activity = assignment.get(session.id)
        if activity is not None:
            gap = abs((activity.start_local.date() - session.date).days)
            session.status = "done" if gap <= MATCH_SAME_DAY_TOLERANCE_DAYS else "moved"
            session.matched_activity_id = activity.id
            counts[session.status] += 1
        elif session.date < today:
            session.status = "missed"
            session.matched_activity_id = None
            counts["missed"] += 1
        else:
            session.status = "planned"
            session.matched_activity_id = None
            counts["planned"] += 1

    # Runs the plan did not ask for. Surfaced rather than dropped: extra
    # training is still training, and silently ignoring it makes the weekly
    # digest understate what was actually done.
    counts["unmatched_runs"] = sum(
        1
        for r in runs
        if r.id not in claimed_runs and r.start_local.date() <= today
    )

    db.commit()
    return counts


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
