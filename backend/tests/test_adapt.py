"""Adaptation rules.

Same property as the planner: given the same history, the same adaptations
fire. The rules operate on model instances rather than queries, so they are
testable in memory without a database.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.constants import (
    EASY_PACE_STREAK,
    LAYOFF_REBUILD_DAYS,
    LONG_RUN_SHORTFALL,
)
from app.models import Activity, PlanSession
from app.planner.adapt import (
    rule_easy_pace_discipline,
    rule_layoff,
    rule_long_run_shortfall,
    rule_missed_sessions,
)

TODAY = date(2026, 9, 7)


def session(
    *,
    day: date,
    kind: str = "easy",
    status: str = "planned",
    week: int = 1,
    target_m: float | None = 5000.0,
    pace_low: float | None = 394.0,
    pace_high: float | None = 425.0,
    activity_id: int | None = None,
) -> PlanSession:
    return PlanSession(
        id=int(day.strftime("%m%d")) + week,
        plan_id=1,
        week_no=week,
        day_of_week=day.weekday(),
        date=day,
        session_type=kind,
        target_distance_m=target_m,
        target_pace_low=pace_low,
        target_pace_high=pace_high,
        status=status,
        matched_activity_id=activity_id,
    )


def activity(*, aid: int, day: date, distance_m: float, moving_s: int) -> Activity:
    return Activity(
        id=aid,
        strava_id=aid,
        athlete_id=1,
        sport_type="Run",
        start_local=datetime.combine(day, datetime.min.time()),
        distance_m=distance_m,
        moving_time_s=moving_s,
    )


# --- missed sessions ------------------------------------------------------


def test_one_missed_session_is_absorbed_silently():
    """Insisting on a perfect week is how a plan gets abandoned."""
    out = rule_missed_sessions([session(day=date(2026, 9, 1), status="missed")], TODAY)
    assert len(out) == 1
    assert out[0].action == "none"
    assert out[0].severity == "info"


def test_two_missed_in_a_week_repeats_it():
    sessions = [
        session(day=date(2026, 9, 1), status="missed"),
        session(day=date(2026, 9, 2), status="missed"),
    ]
    out = rule_missed_sessions(sessions, TODAY)
    assert len(out) == 1
    assert out[0].action == "repeat_week"
    assert out[0].severity == "action"
    assert out[0].data["missed"] == 2


def test_future_sessions_are_never_counted_as_missed():
    future = session(day=TODAY + timedelta(days=3), status="planned")
    assert rule_missed_sessions([future], TODAY) == []


def test_completed_sessions_produce_nothing():
    done = session(day=date(2026, 9, 1), status="done", activity_id=1)
    assert rule_missed_sessions([done], TODAY) == []


# --- layoff ---------------------------------------------------------------


def test_layoff_triggers_a_rebuild():
    runs = [activity(aid=1, day=TODAY - timedelta(days=LAYOFF_REBUILD_DAYS), distance_m=5000, moving_s=1800)]
    out = rule_layoff(runs, TODAY)
    assert out is not None
    assert out.action == "rebuild"
    assert out.data["days"] == LAYOFF_REBUILD_DAYS


def test_a_gap_below_the_threshold_does_not_trigger():
    runs = [activity(aid=1, day=TODAY - timedelta(days=LAYOFF_REBUILD_DAYS - 1), distance_m=5000, moving_s=1800)]
    assert rule_layoff(runs, TODAY) is None


def test_layoff_with_no_history_is_silent():
    assert rule_layoff([], TODAY) is None


# --- long run shortfall ---------------------------------------------------


def test_short_long_run_holds_the_next_step():
    target = 20000.0
    actual = target * (1 - LONG_RUN_SHORTFALL - 0.05)
    s = session(
        day=date(2026, 9, 5), kind="long", status="done", target_m=target, activity_id=9
    )
    acts = {9: activity(aid=9, day=date(2026, 9, 5), distance_m=actual, moving_s=7000)}

    out = rule_long_run_shortfall([s], acts, TODAY)
    assert out is not None
    assert out.action == "hold_long_run"
    assert out.data["shortfall"] == pytest.approx(LONG_RUN_SHORTFALL + 0.05, abs=0.01)


def test_long_run_close_to_target_is_fine():
    s = session(
        day=date(2026, 9, 5), kind="long", status="done", target_m=20000.0, activity_id=9
    )
    acts = {9: activity(aid=9, day=date(2026, 9, 5), distance_m=19000.0, moving_s=7000)}
    assert rule_long_run_shortfall([s], acts, TODAY) is None


def test_only_the_most_recent_long_run_is_judged():
    old = session(
        day=date(2026, 8, 29), kind="long", status="done", target_m=20000.0, activity_id=1, week=1
    )
    new = session(
        day=date(2026, 9, 5), kind="long", status="done", target_m=20000.0, activity_id=2, week=2
    )
    acts = {
        1: activity(aid=1, day=date(2026, 8, 29), distance_m=10000.0, moving_s=4000),
        2: activity(aid=2, day=date(2026, 9, 5), distance_m=19500.0, moving_s=7000),
    }
    assert rule_long_run_shortfall([old, new], acts, TODAY) is None


# --- easy pace discipline -------------------------------------------------


def _easy_streak(count: int, pace_s: float) -> tuple[list[PlanSession], dict[int, Activity]]:
    sessions, acts = [], {}
    for i in range(count):
        day = date(2026, 8, 24) + timedelta(days=i * 2)
        sessions.append(
            session(day=day, kind="easy", status="done", activity_id=100 + i, week=i + 1)
        )
        acts[100 + i] = activity(
            aid=100 + i, day=day, distance_m=5000.0, moving_s=int(pace_s * 5)
        )
    return sessions, acts


def test_three_easy_runs_too_fast_is_flagged():
    sessions, acts = _easy_streak(EASY_PACE_STREAK, pace_s=360.0)  # 6:00/km, band starts 6:34
    out = rule_easy_pace_discipline(sessions, acts, TODAY)
    assert out is not None
    assert out.action == "flag"
    assert len(out.data["runs"]) == EASY_PACE_STREAK


def test_two_too_fast_is_not_yet_a_pattern():
    sessions, acts = _easy_streak(EASY_PACE_STREAK - 1, pace_s=360.0)
    assert rule_easy_pace_discipline(sessions, acts, TODAY) is None


def test_easy_runs_inside_the_band_are_fine():
    sessions, acts = _easy_streak(EASY_PACE_STREAK + 2, pace_s=405.0)  # 6:45/km
    assert rule_easy_pace_discipline(sessions, acts, TODAY) is None


def test_one_disciplined_run_breaks_the_streak():
    sessions, acts = _easy_streak(EASY_PACE_STREAK, pace_s=360.0)
    # Insert a compliant run in the middle; the streak must reset.
    mid_day = date(2026, 8, 25)
    sessions.insert(1, session(day=mid_day, kind="easy", status="done", activity_id=999, week=1))
    acts[999] = activity(aid=999, day=mid_day, distance_m=5000.0, moving_s=int(405 * 5))
    assert rule_easy_pace_discipline(sessions, acts, TODAY) is None


def test_a_session_completed_today_is_visible_to_the_rules():
    """A run finished this morning is finished.

    Filtering completed sessions with `< today` hid it until tomorrow, which
    delayed the shortfall rule past the point where it could stop the next
    long-run step up.
    """
    target = 18400.0
    s = session(
        day=TODAY, kind="long", status="done", target_m=target, activity_id=7
    )
    acts = {7: activity(aid=7, day=TODAY, distance_m=12110.0, moving_s=4600)}

    out = rule_long_run_shortfall([s], acts, TODAY)
    assert out is not None
    assert out.action == "hold_long_run"
    assert out.data["shortfall"] == pytest.approx(0.342, abs=0.01)
