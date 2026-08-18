"""Adaptation rules.

A static plan does not know you missed eleven days in late July. These rules
run nightly and on every ingest, and they compare what was prescribed against
what was actually run.

Every threshold is a constant in `app.constants`. Nothing here is model
judgement — the coach may quote an adaptation, but it does not decide one. That
separation is what makes the advice auditable: given the same activity history,
the same adaptations fire, every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.analytics import load as load_mod
from app.analytics.base import valid_runs
from app.constants import (
    EASY_PACE_STREAK,
    GOAL_PACE_ADVANCE_S,
    GOAL_PACE_ADVANCE_WEEKS,
    LAYOFF_PEAK_REDUCTION,
    LAYOFF_REBUILD_DAYS,
    LONG_RUN_SHORTFALL,
    MISSED_ABSORB_LIMIT,
    MISSED_REPEAT_WEEK,
    TSB_FORCE_RECOVERY,
)
from app.models import Activity, Athlete, Plan, PlanSession
from app.planner import service

Severity = Literal["info", "warning", "action"]
Action = Literal[
    "none",
    "repeat_week",
    "rebuild",
    "hold_long_run",
    "force_recovery",
    "advance_goal_pace",
    "flag",
]


@dataclass
class Adaptation:
    rule: str
    severity: Severity
    action: Action
    message: str
    data: dict = field(default_factory=dict)


def _week_of(plan: Plan, day: date) -> int | None:
    if day < plan.start_date:
        return None
    return (day - plan.start_date).days // 7 + 1


# --- individual rules -----------------------------------------------------


def rule_missed_sessions(sessions: list[PlanSession], today: date) -> list[Adaptation]:
    """One missed session is absorbed. Two in a week is a signal.

    Insisting on a perfect week is how a plan gets abandoned, so the first
    miss deliberately produces nothing at all.
    """
    by_week: dict[int, list[PlanSession]] = {}
    for s in sessions:
        if s.date < today and s.status == "missed":
            by_week.setdefault(s.week_no, []).append(s)

    out: list[Adaptation] = []
    for week_no, missed in sorted(by_week.items()):
        count = len(missed)
        if count <= MISSED_ABSORB_LIMIT:
            out.append(
                Adaptation(
                    rule="missed_sessions",
                    severity="info",
                    action="none",
                    message=(
                        f"Week {week_no}: {count} session missed. Absorbed — no change "
                        f"to the plan."
                    ),
                    data={"week_no": week_no, "missed": count},
                )
            )
        elif count >= MISSED_REPEAT_WEEK:
            out.append(
                Adaptation(
                    rule="missed_sessions",
                    severity="action",
                    action="repeat_week",
                    message=(
                        f"Week {week_no}: {count} sessions missed. Repeat the week rather "
                        f"than stepping the long run up on training that did not happen."
                    ),
                    data={
                        "week_no": week_no,
                        "missed": count,
                        "dates": [s.date.isoformat() for s in missed],
                    },
                )
            )
    return out


def rule_layoff(runs: list[Activity], today: date) -> Adaptation | None:
    """Seven days without running. The failure mode in this athlete's history."""
    if not runs:
        return None

    last = max(r.start_local.date() for r in runs)
    gap = (today - last).days
    if gap < LAYOFF_REBUILD_DAYS:
        return None

    return Adaptation(
        rule="layoff",
        severity="action",
        action="rebuild",
        message=(
            f"{gap} days since the last run ({last}). Rebuild from current fitness "
            f"and pull the peak target back {LAYOFF_PEAK_REDUCTION:.0%} — every fitness "
            f"regression in your history follows a gap like this."
        ),
        data={"days": gap, "last_run": last.isoformat()},
    )


def rule_long_run_shortfall(
    sessions: list[PlanSession], activities: dict[int, Activity], today: date
) -> Adaptation | None:
    """A long run well under target means the next step up is not earned."""
    completed = [
        s
        for s in sessions
        if s.session_type == "long"
        and s.date < today
        and s.status == "done"
        and s.matched_activity_id
        and s.target_distance_m
    ]
    if not completed:
        return None

    latest = max(completed, key=lambda s: s.date)
    actual = activities.get(latest.matched_activity_id or -1)
    if actual is None:
        return None

    shortfall = 1 - actual.distance_m / (latest.target_distance_m or 1)
    if shortfall < LONG_RUN_SHORTFALL:
        return None

    return Adaptation(
        rule="long_run_shortfall",
        severity="action",
        action="hold_long_run",
        message=(
            f"Long run on {latest.date} was {actual.distance_m / 1000:.1f} km against a "
            f"{(latest.target_distance_m or 0) / 1000:.1f} km target ({shortfall:.0%} short). "
            f"Hold the long run at this distance next week instead of stepping up."
        ),
        data={
            "date": latest.date.isoformat(),
            "target_m": latest.target_distance_m,
            "actual_m": actual.distance_m,
            "shortfall": round(shortfall, 3),
        },
    )


def rule_easy_pace_discipline(
    sessions: list[PlanSession], activities: dict[int, Activity], today: date
) -> Adaptation | None:
    """Easy runs run too hard. The most common self-inflicted training error.

    Without heart rate this is the only easy-effort check available, which is
    why it matters more here than it would elsewhere.
    """
    done = sorted(
        (
            s
            for s in sessions
            if s.session_type == "easy"
            and s.date < today
            and s.status == "done"
            and s.matched_activity_id
            and s.target_pace_high
        ),
        key=lambda s: s.date,
    )

    streak: list[tuple[PlanSession, float]] = []
    for s in done:
        actual = activities.get(s.matched_activity_id or -1)
        if actual is None or actual.distance_m <= 0 or actual.moving_time_s <= 0:
            continue
        actual_pace = actual.moving_time_s / (actual.distance_m / 1000)
        if actual_pace < (s.target_pace_low or 0):
            streak.append((s, actual_pace))
        else:
            streak = []

    if len(streak) < EASY_PACE_STREAK:
        return None

    recent = streak[-EASY_PACE_STREAK:]
    return Adaptation(
        rule="easy_pace_discipline",
        severity="warning",
        action="flag",
        message=(
            f"{EASY_PACE_STREAK} easy runs in a row faster than the easy band. Easy days "
            f"being too hard is what makes hard days too easy — and with no heart rate "
            f"recorded, pace is the only check available."
        ),
        data={
            "runs": [
                {"date": s.date.isoformat(), "pace_s_per_km": round(p, 1)} for s, p in recent
            ],
            "band_low_s": recent[-1][0].target_pace_low,
        },
    )


def rule_chronic_fatigue(db: Session, athlete_id: int, today: date) -> Adaptation | None:
    """TSB deep enough that the next quality session will not go well."""
    current = load_mod.current(db, athlete_id, end=today)
    if current is None or current.tsb >= TSB_FORCE_RECOVERY:
        return None

    return Adaptation(
        rule="chronic_fatigue",
        severity="action",
        action="force_recovery",
        message=(
            f"Form (TSB) is {current.tsb:.1f}, below {TSB_FORCE_RECOVERY:.0f}. Take a "
            f"recovery day before the next quality session."
        ),
        data={"tsb": current.tsb, "ctl": current.ctl, "atl": current.atl},
    )


def rule_goal_pace_progression(
    sessions: list[PlanSession], activities: dict[int, Activity], today: date
) -> Adaptation | None:
    """Goal-pace work held at target for three weeks earns a faster target.

    Dormant for the current four-day pattern, which prescribes threshold rather
    than goal-pace sessions. Kept because the rule belongs to the engine, not
    to one week shape.
    """
    hits = [
        s
        for s in sessions
        if s.session_type == "goal_pace"
        and s.date < today
        and s.status == "done"
        and s.matched_activity_id
        and s.target_pace_high
    ]
    if len(hits) < GOAL_PACE_ADVANCE_WEEKS:
        return None

    recent = sorted(hits, key=lambda s: s.date)[-GOAL_PACE_ADVANCE_WEEKS:]
    for s in recent:
        actual = activities.get(s.matched_activity_id or -1)
        if actual is None or actual.distance_m <= 0:
            return None
        if actual.moving_time_s / (actual.distance_m / 1000) > (s.target_pace_high or 0):
            return None

    return Adaptation(
        rule="goal_pace_progression",
        severity="info",
        action="advance_goal_pace",
        message=(
            f"Goal pace hit for {GOAL_PACE_ADVANCE_WEEKS} weeks running. Advance the "
            f"target by {GOAL_PACE_ADVANCE_S:.0f} s/km."
        ),
        data={"advance_s": GOAL_PACE_ADVANCE_S},
    )


# --- runner ---------------------------------------------------------------


def evaluate(
    db: Session, athlete: Athlete, plan: Plan, *, today: date | None = None
) -> list[Adaptation]:
    """Run every rule against the current plan and history."""
    today = today or date.today()

    sessions = service.sessions_for(db, plan.id)
    runs = valid_runs(db, athlete.id)
    activities = {r.id: r for r in runs}

    out: list[Adaptation] = []
    out.extend(rule_missed_sessions(sessions, today))

    for candidate in (
        rule_layoff(runs, today),
        rule_long_run_shortfall(sessions, activities, today),
        rule_easy_pace_discipline(sessions, activities, today),
        rule_chronic_fatigue(db, athlete.id, today),
        rule_goal_pace_progression(sessions, activities, today),
    ):
        if candidate is not None:
            out.append(candidate)

    order = {"action": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda a: order[a.severity])


def digest(
    db: Session, athlete: Athlete, plan: Plan, *, today: date | None = None
) -> dict:
    """A week in review: what was prescribed, what happened, what changes."""
    today = today or date.today()
    week_start = today - timedelta(days=today.weekday())
    week_no = _week_of(plan, week_start)

    sessions = [s for s in service.sessions_for(db, plan.id) if s.week_no == week_no]
    runs = valid_runs(db, athlete.id, week_start, week_start + timedelta(days=6))

    planned_m = sum(s.target_distance_m or 0 for s in sessions)
    actual_m = sum(r.distance_m for r in runs)

    adaptations = evaluate(db, athlete, plan, today=today)

    return {
        "week_no": week_no,
        "week_start": week_start.isoformat(),
        "planned_km": round(planned_m / 1000, 1),
        "actual_km": round(actual_m / 1000, 1),
        "completion": round(actual_m / planned_m, 3) if planned_m else 0.0,
        "sessions_done": sum(1 for s in sessions if s.status == "done"),
        "sessions_total": len(sessions),
        "adaptations": [
            {
                "rule": a.rule,
                "severity": a.severity,
                "action": a.action,
                "message": a.message,
                "data": a.data,
            }
            for a in adaptations
        ],
    }
