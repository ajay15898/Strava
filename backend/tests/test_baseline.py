"""M2's acceptance criterion: the documented baseline reproduces from code.

Values here are the *corrected* baseline. Where they differ from the original
README table the difference is deliberate and named in the test.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.analytics import consistency
from app.analytics.base import run_days, total_km
from tests.conftest import BASELINE_END, BASELINE_START


def test_run_count(runs):
    """55 raw Run records minus 3 duplicates minus 1 noise record."""
    assert len(runs) == 51


def test_total_distance(runs):
    assert total_km(runs) == pytest.approx(290.9, abs=0.05)


def test_deduplication_removes_about_six_percent(normalized, runs):
    raw_km = sum(
        r["distance_m"]
        for r in normalized
        if r["sport_type"] == "Run"
        and BASELINE_START <= r["start_local"].date() <= BASELINE_END
    ) / 1000
    inflation = raw_km / total_km(runs) - 1
    assert inflation == pytest.approx(0.059, abs=0.002)


def test_rolling_averages(runs):
    report = consistency.build_report(runs, BASELINE_START, BASELINE_END)
    assert report.km_per_week_overall == pytest.approx(13.05, abs=0.05)
    assert report.km_per_week_2wk == pytest.approx(23.63, abs=0.05)
    assert report.km_per_week_4wk == pytest.approx(13.58, abs=0.05)


@pytest.mark.parametrize(
    "year,month,km,days",
    [
        # March is 52.0 km over 11 run days, not the README's 52.3 / 12.
        # The 0.3 km is the two duplicate pairs — the original table kept the
        # *longer* recording, the spec's rule keeps the *richer* one. The
        # missing day is 2026-03-18, whose only run is the 19 m noise record.
        (2026, 3, 52.0, 11),
        (2026, 4, 66.8, 12),
        (2026, 5, 32.6, 6),
        # June is 42.2, not 42.4 — the 200.7 m difference is exactly the
        # 2026-06-04 duplicate pair (6880.00 m vs the kept 6679.29 m).
        (2026, 6, 42.2, 7),
        (2026, 7, 50.2, 7),
        (2026, 8, 47.3, 7),
    ],
)
def test_monthly_table(runs, year, month, km, days):
    months = consistency.monthly_summaries(runs, BASELINE_START, BASELINE_END)
    found = next(m for m in months if m.year == year and m.month == month)
    assert found.km == pytest.approx(km, abs=0.05)
    assert found.run_days == days


def test_march_excludes_the_noise_day(runs):
    """2026-03-18 holds only a 19 m record, so it is not a training day.

    The original baseline filtered it from distance but counted it as a run
    day, which is the exact bug `analytics.base` exists to prevent.
    """
    assert date(2026, 3, 18) not in run_days(runs)


def test_gaps(runs):
    gaps = consistency.find_gaps(runs)
    assert [g.days for g in gaps] == [10, 10, 10, 9, 11]
    assert gaps[-1].start.isoformat() == "2026-07-26"
    assert gaps[-1].end.isoformat() == "2026-08-06"


def test_longest_runs(runs):
    longest = sorted(runs, key=lambda r: -r.distance_m)[:2]
    assert longest[0].distance_m == pytest.approx(15008.8)
    assert longest[0].pace_s_per_km == pytest.approx(419.4, abs=0.5)
    assert longest[1].distance_m == pytest.approx(12503.8)
    assert longest[1].pace_s_per_km == pytest.approx(457.9, abs=0.5)


def test_weekly_frequency_last_eight_weeks(runs):
    """The plan assumes 4 runs/week rising to 5. History says otherwise."""
    weeks = consistency.weekly_summaries(runs, BASELINE_END, 8)
    assert [w.run_days for w in weeks] == [2, 2, 2, 2, 1, 0, 4, 3]


def test_no_recent_heart_rate(runs):
    """Not one analysable run in the window recorded heart rate."""
    assert not any(r.has_heartrate for r in runs)
