"""Race prediction: Riegel and Cameron, blended, with a durability penalty.

Two corrections to naive prediction are baked in here, both learned from this
athlete's own history.

1. **Seed from `best_effort`, never from activity `moving_time`.** The 2026
   baseline reported a "24:57 5K" that was actually 4992.59 m of moving time —
   seven metres short of the distance, timed on the more generous clock.
   Strava's own `Fastest5k` for that activity was 25:18. A 21-second error in
   the seed moves the half-marathon projection by about 100 seconds.

2. **Penalise thin long-run volume.** Riegel and Cameron both extrapolate pure
   speed and neither knows whether the athlete has run the distance. With a
   15.01 km longest run against a 21.10 km race, the final 6 km are
   unrehearsed, which is precisely where the classic 1.06 exponent
   over-predicts. See `constants.DURABILITY_*`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.analytics.base import valid_runs
from app.analytics.curves import PacePoint, pace_points
from app.constants import (
    DURABILITY_FULL_RATIO,
    DURABILITY_K,
    DURABILITY_MAX_PENALTY,
    FEASIBILITY_ON_TRACK,
    FEASIBILITY_TIGHT,
    HM_PEAK_WEEKLY_KM,
    RIEGEL_EXPONENT,
)

# Efforts older than this stop describing current fitness.
REFERENCE_WINDOW_DAYS = 90

# A reference effort must be at least this fraction of the target distance.
# Extrapolating a half marathon from a 400 m split is arithmetically possible
# and physiologically meaningless — short efforts wildly over-predict long
# races. At the half-marathon target this floor sits at 4.2 km, so 5 K
# qualifies and the 2-mile best effort does not.
MIN_REFERENCE_FRACTION = 0.2


def riegel(t1: float, d1: float, d2: float, exponent: float = RIEGEL_EXPONENT) -> float:
    return t1 * (d2 / d1) ** exponent


def cameron(t1: float, d1: float, d2: float) -> float:
    """Cameron's formula. Distances in metres, time in seconds.

    Fades harder than Riegel at long distances, which makes the pair a useful
    bracket rather than two spellings of the same guess.
    """

    def a(x: float) -> float:
        return 13.49681 - 0.000030363 * x + 835.7114 / (x**0.7905)

    return (t1 / d1) * (a(d1) / a(d2)) * d2


def durability_penalty(longest_run_m: float, target_m: float) -> float:
    """Fractional inflation applied for an unrehearsed race distance."""
    if target_m <= 0:
        return 0.0
    ratio = longest_run_m / target_m
    if ratio >= DURABILITY_FULL_RATIO:
        return 0.0
    return min((DURABILITY_FULL_RATIO - ratio) * DURABILITY_K, DURABILITY_MAX_PENALTY)


@dataclass
class RacePrediction:
    target_distance_m: float
    reference_distance_m: float
    reference_duration_s: int
    reference_date: date
    reference_effort_type: str
    riegel_s: int
    cameron_s: int
    blended_s: int
    durability_ratio: float
    durability_penalty_pct: float
    predicted_time_s: int
    longest_run_m: float
    used_maximal_reference: bool
    notes: list[str] = field(default_factory=list)

    @property
    def predicted_pace_s_per_km(self) -> float:
        return self.predicted_time_s / (self.target_distance_m / 1000.0)


@dataclass
class Feasibility:
    verdict: str  # on_track | tight | unrealistic
    predicted_time_s: int
    required_weekly_peak_km: float
    current_weekly_km: float
    limiting_factor: str


def choose_reference(
    points: list[PacePoint], today: date, target_m: float
) -> PacePoint | None:
    """Pick the effort that best describes current fitness.

    Selection is by *best demonstrated performance*: among recent efforts long
    enough to extrapolate from, take the one implying the fastest target time.

    This sidesteps the need to detect whether an effort was maximal, which
    cannot be done reliably without heart rate — a 15 K best effort inside a
    15 km easy run spans nearly the whole activity, so any "was the run as hard
    as the effort" test says yes. Ranking by implied performance discards
    sub-maximal efforts automatically, because an easy 15 K implies a slower
    race than a hard 5 K does.
    """
    cutoff = today - timedelta(days=REFERENCE_WINDOW_DAYS)
    floor = target_m * MIN_REFERENCE_FRACTION

    eligible = [p for p in points if p.distance_m >= floor]
    recent = [p for p in eligible if p.activity_date >= cutoff]
    pool = recent or eligible or points
    if not pool:
        return None

    return min(pool, key=lambda p: riegel(p.duration_s, p.distance_m, target_m))


def predict(
    db: Session,
    athlete_id: int,
    target_m: float,
    *,
    today: date | None = None,
) -> RacePrediction | None:
    today = today or date.today()
    points = pace_points(db, athlete_id)
    reference = choose_reference(points, today, target_m)
    if reference is None:
        return None

    runs = valid_runs(db, athlete_id)
    longest = max((r.distance_m for r in runs), default=0.0)

    return build_prediction(reference, target_m, longest)


def build_prediction(
    reference: PacePoint, target_m: float, longest_run_m: float
) -> RacePrediction:
    r = riegel(reference.duration_s, reference.distance_m, target_m)
    c = cameron(reference.duration_s, reference.distance_m, target_m)
    blended = (r + c) / 2

    penalty = durability_penalty(longest_run_m, target_m)
    final = blended * (1 + penalty)

    notes: list[str] = []
    if penalty > 0:
        notes.append(
            f"Durability penalty of {penalty * 100:.1f}% applied: longest run is "
            f"{longest_run_m / 1000:.2f} km against a {target_m / 1000:.2f} km race."
        )

    return RacePrediction(
        target_distance_m=target_m,
        reference_distance_m=reference.distance_m,
        reference_duration_s=reference.duration_s,
        reference_date=reference.activity_date,
        reference_effort_type=reference.effort_type,
        riegel_s=round(r),
        cameron_s=round(c),
        blended_s=round(blended),
        durability_ratio=round(longest_run_m / target_m, 3) if target_m else 0.0,
        durability_penalty_pct=round(penalty * 100, 2),
        predicted_time_s=round(final),
        longest_run_m=longest_run_m,
        used_maximal_reference=reference.is_maximal,
        notes=notes,
    )


def assess(
    prediction: RacePrediction, goal_time_s: int, current_weekly_km: float
) -> Feasibility:
    """Turn a prediction into the verdict the coach must quote verbatim."""
    ratio = prediction.predicted_time_s / goal_time_s

    if ratio <= FEASIBILITY_ON_TRACK:
        verdict = "on_track"
    elif ratio <= FEASIBILITY_TIGHT:
        verdict = "tight"
    else:
        verdict = "unrealistic"

    # Which constraint binds: speed or durability? If the raw blended
    # prediction already clears the goal, the shortfall is endurance, not pace.
    if prediction.blended_s <= goal_time_s and prediction.predicted_time_s > goal_time_s:
        limiting_factor = "long_run_durability"
    elif current_weekly_km < HM_PEAK_WEEKLY_KM * 0.5:
        limiting_factor = "weekly_volume"
    elif prediction.blended_s > goal_time_s:
        limiting_factor = "speed"
    else:
        limiting_factor = "none"

    return Feasibility(
        verdict=verdict,
        predicted_time_s=prediction.predicted_time_s,
        required_weekly_peak_km=HM_PEAK_WEEKLY_KM,
        current_weekly_km=round(current_weekly_km, 2),
        limiting_factor=limiting_factor,
    )
