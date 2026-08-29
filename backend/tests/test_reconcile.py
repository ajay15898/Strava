"""Matching what was actually run onto what was prescribed.

Training slips within a week constantly. The reconciler's job is to recognise
Wednesday's threshold session when it was run on Friday, rather than reporting
a missed session *and* an unattached run — which double-counts one disruption.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.constants import COMPLETED_SESSION_STATUSES
from app.db import Base
from app.models import Activity, Athlete, Plan, PlanSession
from app.planner.service import match_score, reconcile, week_of

MONDAY = date(2026, 8, 17)          # plan start
TABLES = [
    Athlete.__table__,
    Activity.__table__,
    Plan.__table__,
    PlanSession.__table__,
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    with Session(engine) as session:
        session.add(Athlete(id=1, strava_id=1, name="Test"))
        session.add(
            Plan(
                id=1,
                athlete_id=1,
                goal_time_s=7200,
                race_date=MONDAY + timedelta(weeks=7),
                start_date=MONDAY,
                weeks=7,
                engine_version="test",
            )
        )
        session.commit()
        yield session


def add_session(
    db, *, day: date, kind: str, km: float, week: int = 1,
    pace_low: float = 300.0, pace_high: float = 500.0,
) -> PlanSession:
    s = PlanSession(
        plan_id=1, week_no=week, day_of_week=day.weekday(), date=day,
        session_type=kind, target_distance_m=km * 1000,
        target_pace_low=pace_low, target_pace_high=pace_high, status="planned",
    )
    db.add(s)
    db.commit()
    return s


def add_run(db, *, day: date, km: float, pace_s: float = 400.0) -> Activity:
    a = Activity(
        athlete_id=1, strava_id=int(day.strftime("%Y%m%d")) + int(km * 10),
        sport_type="Run", start_local=datetime.combine(day, datetime.min.time()),
        distance_m=km * 1000, moving_time_s=int(km * pace_s),
    )
    db.add(a)
    db.commit()
    return a


# --- the reported problem -------------------------------------------------


def test_a_session_run_later_in_the_week_is_moved_not_missed(db):
    """Wednesday's threshold, actually run on Friday."""
    add_session(db, day=date(2026, 8, 19), kind="threshold", km=7.0)
    add_run(db, day=date(2026, 8, 21), km=7.0)

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))

    session = db.query(PlanSession).one()
    assert session.status == "moved"
    assert session.matched_activity_id is not None
    assert counts["moved"] == 1
    assert counts["missed"] == 0
    assert counts["unmatched_runs"] == 0


def test_a_session_run_on_the_day_is_done(db):
    add_session(db, day=date(2026, 8, 19), kind="threshold", km=7.0)
    add_run(db, day=date(2026, 8, 19), km=7.0)

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.query(PlanSession).one().status == "done"
    assert counts["done"] == 1


def test_one_day_either_side_still_counts_as_done(db):
    """Sunday's long run done on Monday morning is not a schedule change."""
    add_session(db, day=date(2026, 8, 22), kind="long", km=15.0)
    add_run(db, day=date(2026, 8, 23), km=15.0)

    reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.query(PlanSession).one().status == "done"


def test_a_genuinely_missed_session_is_still_missed(db):
    add_session(db, day=date(2026, 8, 19), kind="threshold", km=7.0)

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.query(PlanSession).one().status == "missed"
    assert counts["missed"] == 1


# --- week boundaries ------------------------------------------------------


def test_a_run_cannot_reach_back_into_a_previous_week(db):
    """Otherwise last week's shortfall gets papered over by this week's work,
    and the repeat-the-week rule never fires."""
    add_session(db, day=date(2026, 8, 19), kind="threshold", km=7.0, week=1)
    add_run(db, day=date(2026, 8, 26), km=7.0)   # week 2

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.query(PlanSession).one().status == "missed"
    assert counts["unmatched_runs"] == 1


def test_week_of_maps_dates_onto_the_plan_grid():
    plan = Plan(start_date=MONDAY, weeks=7)
    assert week_of(plan, MONDAY) == 1
    assert week_of(plan, MONDAY + timedelta(days=6)) == 1
    assert week_of(plan, MONDAY + timedelta(days=7)) == 2
    assert week_of(plan, MONDAY - timedelta(days=1)) is None
    assert week_of(plan, MONDAY + timedelta(weeks=8)) is None


# --- picking the right session --------------------------------------------


def test_a_run_claims_the_session_it_actually_resembles(db):
    """A 7 km threshold run on Friday should take Wednesday's threshold slot,
    not Thursday's 5 km easy one, even though Thursday is nearer."""
    threshold = add_session(
        db, day=date(2026, 8, 19), kind="threshold", km=7.0,
        pace_low=310.0, pace_high=330.0,
    )
    easy = add_session(
        db, day=date(2026, 8, 20), kind="easy", km=5.0,
        pace_low=390.0, pace_high=430.0,
    )
    add_run(db, day=date(2026, 8, 21), km=7.0, pace_s=320.0)

    reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.get(PlanSession, threshold.id).status == "moved"
    assert db.get(PlanSession, easy.id).status == "missed"


def test_pace_separates_sessions_of_similar_length(db):
    """Same distance, different intent — pace is what tells them apart."""
    fast = add_session(
        db, day=date(2026, 8, 19), kind="threshold", km=6.0,
        pace_low=310.0, pace_high=330.0,
    )
    slow = add_session(
        db, day=date(2026, 8, 21), kind="easy", km=6.0,
        pace_low=390.0, pace_high=430.0,
    )
    add_run(db, day=date(2026, 8, 20), km=6.0, pace_s=320.0)   # threshold effort

    reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.get(PlanSession, fast.id).status in COMPLETED_SESSION_STATUSES
    assert db.get(PlanSession, slow.id).status == "missed"


def test_one_run_cannot_satisfy_two_sessions(db):
    a = add_session(db, day=date(2026, 8, 18), kind="easy", km=5.0)
    b = add_session(db, day=date(2026, 8, 20), kind="easy", km=5.0)
    add_run(db, day=date(2026, 8, 19), km=5.0)

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    statuses = [db.get(PlanSession, a.id).status, db.get(PlanSession, b.id).status]

    # One run, one session satisfied. Both sit a day either side, so whichever
    # wins counts as done rather than moved.
    assert sorted(statuses) == ["done", "missed"]
    assert counts["missed"] == 1
    assert counts["unmatched_runs"] == 0


# --- extra work -----------------------------------------------------------


def test_runs_the_plan_did_not_ask_for_are_reported(db):
    """Extra training is still training; dropping it understates the week."""
    add_session(db, day=date(2026, 8, 19), kind="threshold", km=7.0)
    add_run(db, day=date(2026, 8, 19), km=7.0)
    add_run(db, day=date(2026, 8, 20), km=12.0)   # unplanned

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert counts["done"] == 1
    assert counts["unmatched_runs"] == 1


def test_a_wildly_different_distance_does_not_match(db):
    add_session(db, day=date(2026, 8, 19), kind="threshold", km=7.0)
    add_run(db, day=date(2026, 8, 20), km=2.0)

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.query(PlanSession).one().status == "missed"
    assert counts["unmatched_runs"] == 1


# --- properties -----------------------------------------------------------


def test_reconcile_is_idempotent(db):
    add_session(db, day=date(2026, 8, 19), kind="threshold", km=7.0)
    add_run(db, day=date(2026, 8, 21), km=7.0)

    first = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    second = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert first == second


def test_future_sessions_are_never_marked_missed(db):
    future = date.today() + timedelta(days=30)
    add_session(db, day=future, kind="long", km=18.0, week=week_of(
        Plan(start_date=MONDAY, weeks=7), future
    ) or 7)

    reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.query(PlanSession).one().status == "planned"


def test_score_rejects_an_implausible_distance():
    s = PlanSession(target_distance_m=7000.0, date=date(2026, 8, 19))
    a = Activity(
        distance_m=2000.0, moving_time_s=800,
        start_local=datetime(2026, 8, 19),
    )
    assert match_score(s, a) is None


def test_score_prefers_the_closer_day_when_all_else_is_equal():
    s = PlanSession(
        target_distance_m=7000.0, date=date(2026, 8, 19),
        target_pace_low=300.0, target_pace_high=500.0,
    )
    near = Activity(distance_m=7000.0, moving_time_s=2800, start_local=datetime(2026, 8, 20))
    far = Activity(distance_m=7000.0, moving_time_s=2800, start_local=datetime(2026, 8, 22))
    assert match_score(s, near) > match_score(s, far)


# --- short sessions -------------------------------------------------------


def test_a_short_long_run_still_matches_its_session(db):
    """Cutting a long run short is the normal failure mode.

    It must still match, because the long-run-shortfall rule only inspects
    matched sessions — leaving it unmatched hides the attempt from the very
    rule written to catch it.
    """
    s = add_session(db, day=date(2026, 8, 22), kind="long", km=18.4)
    add_run(db, day=date(2026, 8, 22), km=12.1)

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.get(PlanSession, s.id).status in COMPLETED_SESSION_STATUSES
    assert counts["unmatched_runs"] == 0


def test_running_far_over_the_prescription_does_not_match(db):
    """Overshooting by half suggests a different session, not this one."""
    add_session(db, day=date(2026, 8, 18), kind="easy", km=8.0)
    add_run(db, day=date(2026, 8, 18), km=14.0)

    counts = reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.query(PlanSession).one().status == "missed"
    assert counts["unmatched_runs"] == 1


def test_a_short_run_prefers_the_session_it_best_fits(db):
    """A 12 km run should take the long run, not the 8 km easy one it
    overshoots."""
    long_run = add_session(db, day=date(2026, 8, 22), kind="long", km=18.4)
    easy = add_session(db, day=date(2026, 8, 23), kind="easy", km=8.0)
    add_run(db, day=date(2026, 8, 22), km=12.1)

    reconcile(db, db.get(Athlete, 1), db.get(Plan, 1))
    assert db.get(PlanSession, long_run.id).status in COMPLETED_SESSION_STATUSES
    assert db.get(PlanSession, easy.id).status == "missed"
