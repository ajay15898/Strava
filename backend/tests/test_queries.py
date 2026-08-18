"""End-to-end exercise of the ingest path and the SQLAlchemy query layer.

Runs on in-memory SQLite. Only the tables that avoid Postgres-specific JSONB
are created — `activity`, `best_effort`, `athlete` — which is exactly the set
the ingest and analytics paths touch. That keeps these tests runnable with no
container while still covering the real queries, which the pure-function tests
in test_baseline.py cannot reach.

The Postgres-only surface (streams, plans, coach messages) is covered by the
Alembic migration instead.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.analytics import load, predict
from app.analytics.base import total_km, valid_runs
from app.analytics.curves import curve
from app.constants import HALF_MARATHON_M
from app.db import Base
from app.models import Activity, Athlete, BestEffort
from app.strava.sync import (
    apply_dedup,
    normalize_activity,
    store_best_efforts,
    upsert_activity,
)
from tests.fixtures import RAW, strava_activities

TABLES = [Athlete.__table__, Activity.__table__, BestEffort.__table__]


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    with Session(engine) as session:
        athlete = Athlete(
            strava_id=457040170,
            name="Ajay Raja Ram",
            goal_race_distance_m=HALF_MARATHON_M,
            goal_time_s=7200,
            goal_race_date=date(2026, 11, 29),
        )
        session.add(athlete)
        session.flush()

        for raw in strava_activities():
            activity = upsert_activity(session, athlete.id, normalize_activity(raw))
            if raw.get("best_efforts"):
                session.flush()
                store_best_efforts(session, activity, raw)
        session.commit()

        apply_dedup(session, athlete.id)
        yield session


@pytest.fixture
def athlete_id(db: Session) -> int:
    return db.query(Athlete).one().id


def test_ingest_flags_duplicates_in_the_database(db, athlete_id):
    flagged = db.query(Activity).filter(Activity.is_duplicate.is_(True)).all()
    assert {a.strava_id for a in flagged} == {17720996478, 17728305812, 18779723440}
    # Never hard-deleted — every ingested row remains queryable.
    assert db.query(Activity).count() == len(RAW)
    for a in flagged:
        assert a.duplicate_of_strava_id is not None


def test_valid_runs_reproduces_the_baseline(db, athlete_id):
    runs = valid_runs(db, athlete_id, date(2026, 3, 14), date(2026, 8, 16))
    assert len(runs) == 51
    assert total_km(runs) == pytest.approx(290.9, abs=0.05)


def test_valid_runs_excludes_walks_and_the_noise_record(db, athlete_id):
    runs = valid_runs(db, athlete_id)
    assert all(r.sport_type == "Run" for r in runs)
    assert all(r.distance_m >= 500 for r in runs)
    assert 17768304740 not in {r.strava_id for r in runs}


def test_pace_curve_is_built_from_best_efforts(db, athlete_id):
    points = curve(db, athlete_id)
    by_type = {p.effort_type: p for p in points}

    # Best 5 K across the history is the 2026-08-15 PR at 1518 s — not the
    # 1986 s split from the long run, and not the activity's 1497 s moving time.
    assert by_type["Fastest5k"].duration_s == 1518
    assert by_type["Fastest15k"].duration_s == 6376
    assert [p.distance_m for p in points] == sorted(p.distance_m for p in points)


def test_prediction_end_to_end(db, athlete_id):
    p = predict.predict(db, athlete_id, HALF_MARATHON_M, today=date(2026, 8, 16))
    assert p is not None
    assert p.reference_effort_type == "Fastest5k"
    assert p.reference_duration_s == 1518
    assert p.longest_run_m == pytest.approx(15008.8)
    assert p.durability_penalty_pct == pytest.approx(4.16, abs=0.05)
    assert p.predicted_time_s > 7200


def test_feasibility_end_to_end(db, athlete_id):
    p = predict.predict(db, athlete_id, HALF_MARATHON_M, today=date(2026, 8, 16))
    f = predict.assess(p, goal_time_s=7200, current_weekly_km=13.58)
    assert f.verdict in {"tight", "unrealistic"}
    assert f.limiting_factor == "long_run_durability"


def test_load_series_is_continuous_and_includes_rest_days(db, athlete_id):
    series = load.series(db, athlete_id, start=date(2026, 3, 14), end=date(2026, 8, 16))
    assert len(series) == 156
    assert [d.date for d in series] == sorted(d.date for d in series)

    # The 11-day gap ending 2026-08-06 must show as zero-load days, or the
    # exponential averages never decay.
    gap = [d for d in series if date(2026, 7, 27) <= d.date <= date(2026, 8, 5)]
    assert all(d.load == 0.0 for d in gap)
    assert gap[-1].ctl < gap[0].ctl


def test_heart_rate_flags_are_derived_not_hardcoded(db, athlete_id):
    assert load.last_heartrate_date(db, athlete_id) is None
    assert load.has_recent_heartrate(db, athlete_id) is False
