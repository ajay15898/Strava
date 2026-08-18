"""Prediction, and the seeding bug it exists to prevent."""

from __future__ import annotations

from datetime import date

import pytest

from app.analytics.curves import PacePoint, canonical_distance
from app.analytics.predict import (
    assess,
    build_prediction,
    cameron,
    choose_reference,
    durability_penalty,
    riegel,
)
from app.constants import HALF_MARATHON_M
from tests.fixtures import BEST_EFFORTS

LONGEST_RUN_M = 15008.8


def point(effort_type: str, seconds: int, when: date, activity_id: int = 1) -> PacePoint:
    distance = canonical_distance(effort_type)
    assert distance is not None
    return PacePoint(
        distance_m=distance,
        duration_s=seconds,
        activity_id=activity_id,
        activity_date=when,
        effort_type=effort_type,
        is_maximal=False,
    )


@pytest.fixture
def points() -> list[PacePoint]:
    """Every best effort in the fixture, as the curve would produce them."""
    dates = {
        19746966449: date(2026, 8, 15),
        19650081711: date(2026, 8, 8),
        19264512812: date(2026, 7, 11),
    }
    return [
        point(name, secs, dates[activity_id], activity_id)
        for activity_id, efforts in BEST_EFFORTS.items()
        for name, secs in efforts
    ]


# --- the seeding correction ---------------------------------------------


def test_riegel_from_the_measured_5k_not_the_moving_time():
    """The activity's moving_time was 1497 s over 4992.59 m — not a 5 K.

    Strava's own Fastest5k for that run is 1518 s. Seeding from the wrong one
    moves the half-marathon projection by about a minute and a half.
    """
    measured = riegel(1518, 5000, HALF_MARATHON_M)
    moving_time = riegel(1497, 4992.59, HALF_MARATHON_M)
    assert measured == pytest.approx(6983.6, abs=1.0)
    assert measured - moving_time == pytest.approx(88.0, abs=3.0)


def test_reference_is_the_hard_5k_not_the_easy_15k(points):
    """The 15 K best effort is longer but came from an easy long run.

    Ranking by implied performance must prefer the 5 K PR over it.
    """
    ref = choose_reference(points, date(2026, 8, 16), HALF_MARATHON_M)
    assert ref is not None
    assert ref.effort_type == "Fastest5k"
    assert ref.duration_s == 1518
    assert ref.activity_date == date(2026, 8, 15)


def test_short_efforts_are_excluded_from_reference(points):
    """The distance floor keeps sprints out of contention.

    This athlete's own 400 m (109 s) happens to project *slower* than their
    5 K, so performance-ranking alone would already discard it. The floor
    exists for the case where it would not: a genuinely sharp short effort
    wins on projected time while saying nothing about 21 km.
    """
    sprinter = [*points, point("Fastest400", 60, date(2026, 8, 15), activity_id=99)]

    assert riegel(60, 400, HALF_MARATHON_M) < riegel(1518, 5000, HALF_MARATHON_M)

    ref = choose_reference(sprinter, date(2026, 8, 16), HALF_MARATHON_M)
    assert ref is not None
    assert ref.distance_m >= HALF_MARATHON_M * 0.2
    assert ref.effort_type == "Fastest5k"


def test_both_best_effort_spellings_resolve():
    """Strava v3 returns "5K"; some wrappers return "Fastest5k".

    Confirmed against both sources — the live API produced `5K`, `10K`, `1K`,
    `1 mile`, while the MCP connector produced `Fastest5k`. A map that handled
    only one spelling would silently yield an empty pace curve.
    """
    for a, b in [("5K", "Fastest5k"), ("10K", "Fastest10k"), ("1K", "Fastest1k")]:
        assert canonical_distance(a) == canonical_distance(b) is not None
    assert canonical_distance("1 mile") == pytest.approx(1609.34)
    assert canonical_distance("1/2 mile") == pytest.approx(804.67)
    assert canonical_distance("nonsense") is None


# --- formulae -------------------------------------------------------------


def test_riegel_and_cameron_agree_closely_over_this_range():
    """Two independent models, blended to avoid trusting either alone.

    Over 5 K to half marathon they land within about a percent of each other,
    which is why the durability penalty — not the choice of formula — is what
    actually moves this athlete's verdict.
    """
    r = riegel(1518, 5000, HALF_MARATHON_M)
    c = cameron(1518, 5000, HALF_MARATHON_M)
    assert abs(c - r) / r < 0.02
    assert 6900 < r < 7050
    assert 6900 < c < 7050


def test_durability_penalty_at_the_current_baseline():
    penalty = durability_penalty(LONGEST_RUN_M, HALF_MARATHON_M)
    assert penalty == pytest.approx(0.0416, abs=0.0005)


def test_no_penalty_once_the_long_run_is_close_enough():
    assert durability_penalty(HALF_MARATHON_M * 0.85, HALF_MARATHON_M) == 0.0
    assert durability_penalty(HALF_MARATHON_M, HALF_MARATHON_M) == 0.0


def test_penalty_is_capped():
    assert durability_penalty(0.0, HALF_MARATHON_M) == pytest.approx(0.15)


# --- end to end -----------------------------------------------------------


def test_prediction_straddles_the_goal(points):
    """The headline claim was ~1:54. On measured data, with durability
    accounted for, sub-2:00 is not yet supported."""
    ref = choose_reference(points, date(2026, 8, 16), HALF_MARATHON_M)
    p = build_prediction(ref, HALF_MARATHON_M, LONGEST_RUN_M)

    assert p.reference_duration_s == 1518
    assert p.riegel_s == pytest.approx(6984, abs=2)
    assert p.durability_ratio == pytest.approx(0.711, abs=0.002)
    assert p.durability_penalty_pct == pytest.approx(4.16, abs=0.05)
    # Blended and penalised, the projection lands beyond two hours.
    assert p.predicted_time_s > 7200
    assert p.notes


def test_feasibility_names_durability_as_the_limiter(points):
    """Raw speed clears 2:00; the durability penalty is what pushes it over.

    That makes durability the proximate limiter, not weekly volume — a more
    actionable answer, because it points at the long run specifically rather
    than at total mileage in general.
    """
    ref = choose_reference(points, date(2026, 8, 16), HALF_MARATHON_M)
    p = build_prediction(ref, HALF_MARATHON_M, LONGEST_RUN_M)
    f = assess(p, goal_time_s=7200, current_weekly_km=13.58)

    assert f.verdict in {"tight", "unrealistic"}
    assert f.current_weekly_km == pytest.approx(13.58)
    assert f.required_weekly_peak_km == 45.0
    assert p.blended_s <= 7200 < p.predicted_time_s
    assert f.limiting_factor == "long_run_durability"


def test_feasibility_names_volume_when_speed_is_short_too():
    """With no durability shortfall and a genuinely slow reference, the
    limiter falls back to weekly volume."""
    ref = point("Fastest5k", 1800, date(2026, 8, 15))
    p = build_prediction(ref, HALF_MARATHON_M, longest_run_m=HALF_MARATHON_M)
    f = assess(p, goal_time_s=7200, current_weekly_km=13.58)

    assert p.durability_penalty_pct == 0.0
    assert p.predicted_time_s > 7200
    assert f.verdict == "unrealistic"
    assert f.limiting_factor == "weekly_volume"


def test_on_track_when_prediction_clears_the_goal():
    ref = point("Fastest10k", 2700, date(2026, 8, 15))
    p = build_prediction(ref, HALF_MARATHON_M, longest_run_m=HALF_MARATHON_M)
    f = assess(p, goal_time_s=7200, current_weekly_km=45.0)
    assert f.verdict == "on_track"
    assert f.limiting_factor == "none"
