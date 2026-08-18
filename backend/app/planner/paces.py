"""Training paces, derived from current fitness rather than prescribed.

Everything is anchored to one measured reference effort. Hardcoding a pace
table would mean the plan stops matching the athlete the moment they get
fitter or lose form — and, more immediately, it was a hardcoded "5:00/km 5K"
that carried the original spec's seeding error into every prescribed band.

Goal pace is the exception: it is arithmetic on the goal itself, not a
derivation from fitness. If goal pace lands faster than threshold pace, the
goal is not a pace problem, and `PaceTable.goal_is_beyond_threshold` says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.constants import PACE_MULTIPLIERS


@dataclass(frozen=True)
class PaceBand:
    """A prescribed pace range, in seconds per kilometre."""

    low: float  # faster end
    high: float  # slower end

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2

    def format(self) -> str:
        return f"{fmt_pace(self.low)}–{fmt_pace(self.high)}/km"

    def contains(self, seconds_per_km: float) -> bool:
        return self.low <= seconds_per_km <= self.high


def fmt_pace(seconds_per_km: float) -> str:
    s = int(round(seconds_per_km))
    return f"{s // 60}:{s % 60:02d}"


@dataclass(frozen=True)
class PaceTable:
    reference_distance_m: float
    reference_duration_s: int
    race_pace_5k: float

    recovery: PaceBand
    easy: PaceBand
    long: PaceBand
    goal: PaceBand
    threshold: PaceBand
    interval: PaceBand
    strides: PaceBand

    @property
    def goal_is_beyond_threshold(self) -> bool:
        """Goal pace faster than threshold means the goal outruns current fitness."""
        return self.goal.mid < self.threshold.mid

    def band(self, name: str) -> PaceBand:
        return getattr(self, name)


def equivalent_5k_pace(distance_m: float, duration_s: float) -> float:
    """Convert any reference effort to an equivalent 5 K pace via Riegel.

    Anchoring everything to a single canonical distance keeps the multipliers
    meaningful when the reference happens to be a 10 K or a mile.
    """
    from app.constants import RIEGEL_EXPONENT

    equivalent_5k_s = duration_s * (5000.0 / distance_m) ** RIEGEL_EXPONENT
    return equivalent_5k_s / 5.0


def derive(
    *,
    reference_distance_m: float,
    reference_duration_s: int,
    goal_distance_m: float,
    goal_time_s: int,
    goal_tolerance_s: float = 5.0,
) -> PaceTable:
    """Build the full pace table from one effort plus the goal."""
    p5k = equivalent_5k_pace(reference_distance_m, reference_duration_s)

    def band(name: str) -> PaceBand:
        lo, hi = PACE_MULTIPLIERS[name]
        return PaceBand(low=p5k * lo, high=p5k * hi)

    goal_pace = goal_time_s / (goal_distance_m / 1000.0)

    return PaceTable(
        reference_distance_m=reference_distance_m,
        reference_duration_s=reference_duration_s,
        race_pace_5k=p5k,
        recovery=band("recovery"),
        easy=band("easy"),
        long=band("long"),
        # A band around goal pace, not a single number — nobody holds a pace to
        # the second for 21 km, and a point target invites over-running early.
        goal=PaceBand(low=goal_pace - goal_tolerance_s, high=goal_pace + goal_tolerance_s),
        threshold=band("threshold"),
        interval=band("interval"),
        strides=band("strides"),
    )
