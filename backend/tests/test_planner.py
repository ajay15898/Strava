"""The deterministic planner.

The load-bearing property is reproducibility: same inputs, same plan, always.
Everything else the coach says about a plan rests on being able to regenerate
it and get the same answer back.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

import pytest

from app.constants import (
    LONG_RUN_CEILING_M,
    LONG_RUN_STEP_CAP,
    LONG_RUN_WEEK_SHARE,
    MIN_PLAN_WEEKS,
)
from app.planner import paces
from app.planner.engine import (
    FitnessSnapshot,
    PlanTooShort,
    generate,
    plan_window,
    starting_weekly_km,
)
from app.planner.phases import Phase, phase_sequence

HM = 21097.5
GOAL_S = 7200
RACE = date(2026, 10, 4)
TODAY = date(2026, 8, 18)

# The athlete's real state on 2026-08-18.
FITNESS = FitnessSnapshot(
    reference_distance_m=5000.0,
    reference_duration_s=1518,
    longest_run_m=15008.8,
    weekly_km_2wk=23.63,
    weekly_km_4wk=13.58,
)


@pytest.fixture
def plan():
    return generate(
        fitness=FITNESS,
        goal_distance_m=HM,
        goal_time_s=GOAL_S,
        race_date=RACE,
        today=TODAY,
        sessions_per_week=4,
    )


# --- window ---------------------------------------------------------------


def test_plan_window_starts_next_monday_and_counts_whole_weeks():
    start, weeks = plan_window(TODAY, RACE)
    assert start == date(2026, 8, 24)
    assert start.weekday() == 0
    assert weeks == 6


def test_rejects_a_window_below_the_floor():
    with pytest.raises(PlanTooShort, match=str(MIN_PLAN_WEEKS)):
        generate(
            fitness=FITNESS,
            goal_distance_m=HM,
            goal_time_s=GOAL_S,
            race_date=date(2026, 9, 13),  # ~3 weeks out
            today=TODAY,
        )


# --- paces ----------------------------------------------------------------


def test_paces_derive_from_the_measured_effort_not_a_table():
    t = paces.derive(
        reference_distance_m=5000.0,
        reference_duration_s=1518,
        goal_distance_m=HM,
        goal_time_s=GOAL_S,
    )
    # 25:18 for 5 K is 5:04/km.
    assert t.race_pace_5k == pytest.approx(303.6, abs=0.5)
    # Goal pace is arithmetic on the goal, not a derivation.
    assert t.goal.mid == pytest.approx(GOAL_S / (HM / 1000), abs=0.1)
    # Easy must be slower than threshold, which must be slower than interval.
    assert t.easy.low > t.threshold.high > t.interval.high
    assert not t.goal_is_beyond_threshold


def test_pace_bands_agree_with_the_athletes_strava_zones():
    """Derived threshold should land inside the Z3/Z4 band of 5:12-5:47/km."""
    t = paces.derive(
        reference_distance_m=5000.0,
        reference_duration_s=1518,
        goal_distance_m=HM,
        goal_time_s=GOAL_S,
    )
    assert 312 <= t.threshold.mid <= 347


def test_a_slower_reference_yields_slower_prescriptions():
    fast = paces.derive(
        reference_distance_m=5000.0, reference_duration_s=1518,
        goal_distance_m=HM, goal_time_s=GOAL_S,
    )
    slow = paces.derive(
        reference_distance_m=5000.0, reference_duration_s=1800,
        goal_distance_m=HM, goal_time_s=GOAL_S,
    )
    assert slow.easy.mid > fast.easy.mid
    assert slow.threshold.mid > fast.threshold.mid
    # ...but goal pace is unchanged, because the goal did not change.
    assert slow.goal.mid == pytest.approx(fast.goal.mid)


def test_goal_beyond_threshold_is_detected():
    t = paces.derive(
        reference_distance_m=5000.0,
        reference_duration_s=1800,  # 30:00 5K
        goal_distance_m=HM,
        goal_time_s=5400,  # 1:30 half — far beyond that fitness
    )
    assert t.goal_is_beyond_threshold


# --- structure ------------------------------------------------------------


def test_six_week_shape_is_build_then_one_taper_then_race(plan):
    assert plan.weeks == 6
    assert [w.phase for w in plan.week_plans] == [
        "build", "build", "build", "build", "taper", "race",
    ]
    assert plan.compressed


def test_longer_plans_keep_a_base_phase():
    seq = phase_sequence(14)
    assert Phase.BASE in seq
    assert seq[-1] is Phase.RACE
    assert seq.count(Phase.TAPER) == 1
    assert len(seq) == 14


def test_four_sessions_a_week_on_the_prescribed_days(plan):
    for week in plan.week_plans[:-1]:
        assert len(week.sessions) == 4
        assert [s.day_of_week for s in week.sessions] == [1, 2, 5, 6]  # Tue Wed Sat Sun

    kinds = [s.session_type for s in plan.week_plans[0].sessions]
    assert kinds == ["easy", "threshold", "long", "easy"]
    assert kinds.count("threshold") == 1, "one quality day, not two"


def test_quality_day_is_never_adjacent_to_the_long_run(plan):
    """A threshold session the day before the long run compromises the one
    session that actually moves the projection."""
    for week in plan.week_plans:
        by_day = {s.day_of_week: s.session_type for s in week.sessions}
        for day, kind in by_day.items():
            if kind == "long":
                assert by_day.get(day - 1) != "threshold"


def test_easy_run_follows_the_long_run(plan):
    """Running easy on yesterday's legs is a durability builder, not a cost."""
    week = plan.week_plans[0]
    by_day = {s.day_of_week: s.session_type for s in week.sessions}
    long_day = next(d for d, k in by_day.items() if k == "long")
    assert by_day.get(long_day + 1) == "easy"


def test_race_week_ends_on_race_day(plan):
    race_week = plan.week_plans[-1]
    final = race_week.sessions[-1]
    assert final.session_type == "race"
    assert final.date == RACE
    assert final.target_distance_m == pytest.approx(HM, abs=10)


# --- progression ----------------------------------------------------------


def test_long_run_never_steps_more_than_the_cap(plan):
    longs = [w.long_run_m for w in plan.week_plans if w.phase == "build"]
    for previous, nxt in zip(longs, longs[1:]):
        assert nxt <= previous * (1 + LONG_RUN_STEP_CAP) + 1


def test_long_run_respects_the_ceiling(plan):
    assert max(w.long_run_m for w in plan.week_plans) <= LONG_RUN_CEILING_M


def test_long_run_clears_the_durability_threshold(plan):
    """The whole point of this block: get past 17.93 km before the taper."""
    from app.constants import DURABILITY_FULL_RATIO

    needed = DURABILITY_FULL_RATIO * HM
    assert plan.peak_long_run_m >= needed


def test_weekly_volume_is_derived_from_the_long_run(plan):
    """Volume follows the long run, not the other way round.

    Sized off a 70% share the other three sessions came out at 2-3 km, which is
    not a training stimulus.
    """
    for week in plan.week_plans:
        if week.phase != "build":
            continue
        assert week.long_run_m / (week.target_km * 1000) == pytest.approx(
            LONG_RUN_WEEK_SHARE, abs=0.02
        )


def test_no_build_session_is_trivially_short(plan):
    for week in plan.week_plans:
        if week.phase != "build":
            continue
        for s in week.sessions:
            if s.session_type in {"easy", "threshold"}:
                assert s.target_distance_m >= 4000


def test_taper_cuts_volume_but_keeps_the_quality_session(plan):
    build_peak = max(w.target_km for w in plan.week_plans if w.phase == "build")
    taper = next(w for w in plan.week_plans if w.phase == "taper")
    assert taper.target_km < build_peak
    assert any(s.session_type == "threshold" for s in taper.sessions)


def test_compressed_plan_warns_about_both_real_costs(plan):
    joined = " ".join(plan.warnings)
    assert "Compressed build" in joined
    assert "faster than the 8% cap" in joined


def test_starting_volume_prefers_the_more_recent_average():
    """The 4-week figure spans an 11-day gap, so it describes an interruption."""
    assert starting_weekly_km(FITNESS) == pytest.approx(23.63)
    # ...but the floor still applies to someone genuinely starting out.
    quiet = FitnessSnapshot(5000.0, 1518, 8000.0, 4.0, 3.0)
    assert starting_weekly_km(quiet) == 20.0


# --- determinism ----------------------------------------------------------


def test_generation_is_deterministic():
    kwargs = dict(
        fitness=FITNESS,
        goal_distance_m=HM,
        goal_time_s=GOAL_S,
        race_date=RACE,
        today=TODAY,
        sessions_per_week=4,
    )
    first, second = generate(**kwargs), generate(**kwargs)
    assert asdict(first) == asdict(second)


def test_different_fitness_produces_a_different_plan():
    fitter = FitnessSnapshot(5000.0, 1400, 18000.0, 40.0, 38.0)
    a = generate(
        fitness=FITNESS, goal_distance_m=HM, goal_time_s=GOAL_S,
        race_date=RACE, today=TODAY,
    )
    b = generate(
        fitness=fitter, goal_distance_m=HM, goal_time_s=GOAL_S,
        race_date=RACE, today=TODAY,
    )
    assert b.peak_weekly_km > a.peak_weekly_km
    assert b.pace_table.threshold.mid < a.pace_table.threshold.mid


# --- configurable pattern -------------------------------------------------


def test_fixed_commitments_keep_their_distance_and_pace():
    """A club session and a social run are constraints, not suggestions."""
    from app.planner.phases import pattern_from_config

    pattern = pattern_from_config([
        {"day": 1, "type": "easy"},
        {"day": 2, "type": "threshold", "fixed_distance_m": 7000},
        {"day": 5, "type": "long"},
        {"day": 6, "type": "easy", "fixed_distance_m": 8000,
         "fixed_pace_s": 410, "label": "Social run"},
    ])
    p = generate(
        fitness=FITNESS, goal_distance_m=HM, goal_time_s=GOAL_S,
        race_date=RACE, today=TODAY, pattern=pattern,
    )
    for week in p.week_plans:
        if week.phase != "build":
            continue
        by_day = {s.day_of_week: s for s in week.sessions}
        assert by_day[2].target_distance_m == pytest.approx(7000)
        assert by_day[6].target_distance_m == pytest.approx(8000)
        # A fixed pace overrides the derived band entirely.
        assert by_day[6].target_pace_low == by_day[6].target_pace_high == 410


def test_flexible_sessions_grow_with_the_long_run():
    from app.planner.phases import pattern_from_config

    pattern = pattern_from_config([
        {"day": 1, "type": "easy", "long_run_fraction": 0.30},
        {"day": 2, "type": "threshold", "fixed_distance_m": 7000},
        {"day": 5, "type": "long"},
        {"day": 6, "type": "easy", "fixed_distance_m": 8000},
    ])
    p = generate(
        fitness=FITNESS, goal_distance_m=HM, goal_time_s=GOAL_S,
        race_date=RACE, today=TODAY, pattern=pattern,
    )
    builds = [w for w in p.week_plans if w.phase == "build"]
    easies = [next(s for s in w.sessions if s.day_of_week == 1) for w in builds]
    assert easies[-1].target_distance_m >= easies[0].target_distance_m


def test_threshold_before_long_run_is_flagged():
    """The arrangement the athlete first proposed: Fri hard, Sat long."""
    from app.planner.phases import pattern_from_config

    risky = pattern_from_config([
        {"day": 1, "type": "easy"},
        {"day": 4, "type": "threshold", "fixed_distance_m": 7000},
        {"day": 5, "type": "long"},
        {"day": 6, "type": "easy", "fixed_distance_m": 8000},
    ])
    p = generate(
        fitness=FITNESS, goal_distance_m=HM, goal_time_s=GOAL_S,
        race_date=RACE, today=TODAY, pattern=risky,
    )
    assert any("tired legs" in w for w in p.warnings)


def test_default_pattern_raises_no_ordering_warning(plan):
    assert not any("tired legs" in w for w in plan.warnings)


# --- starting this week ---------------------------------------------------


def test_start_this_week_recovers_a_full_week():
    later, weeks_later = plan_window(TODAY, RACE, start_this_week=False)
    now, weeks_now = plan_window(TODAY, RACE, start_this_week=True)

    assert later == date(2026, 8, 24)
    assert now == date(2026, 8, 17)   # the Monday just gone
    assert now.weekday() == 0
    assert weeks_now == weeks_later + 1 == 7


def test_week_one_does_not_stack_a_long_run_step_on_a_volume_jump():
    """Week one meets the athlete where they are; progression starts in W2."""
    p = generate(
        fitness=FITNESS, goal_distance_m=HM, goal_time_s=GOAL_S,
        race_date=RACE, today=TODAY, start_this_week=True,
    )
    assert p.week_plans[0].long_run_m == pytest.approx(FITNESS.longest_run_m, abs=10)
    assert p.week_plans[1].long_run_m > p.week_plans[0].long_run_m
