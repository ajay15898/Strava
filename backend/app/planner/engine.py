"""Deterministic plan generation.

Given (fitness, goal, race date, constraints) this returns a full plan with no
model call anywhere in the path. Same inputs, same output, every time — that
property is what lets the coach quote the plan instead of inventing one, and
what makes a past plan auditable after the fact.

Two things drive the numbers, in this order:

1. **The long run.** For this athlete the projection moves with long-run
   distance and little else — 15.01 km to 17.93 km removes the entire
   durability penalty. So the long run progresses on its own capped schedule.
2. **Everything else follows.** Fixed commitments keep their distance; flexible
   sessions are sized as a fraction of that week's long run. Weekly volume is
   the *sum* of the week, not a target the sessions get fitted into.

Sizing it the other way round produced 2-3 km easy runs, which is not a
training stimulus. `HM_PEAK_WEEKLY_KM` is deliberately not consulted: it
describes a typical build, not this athlete's binding constraint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.constants import (
    COMPRESSED_PLAN_WEEKS,
    DOWN_WEEK_EVERY,
    DOWN_WEEK_FACTOR,
    LONG_RUN_CEILING_M,
    LONG_RUN_STEP_CAP,
    LONG_RUN_WEEK_SHARE,
    MIN_PLAN_WEEKS,
    MIN_SESSION_DISTANCE_M,
    MIN_START_WEEKLY_KM,
    RACE_WEEK_VOLUME_FACTOR,
    TAPER_VOLUME_FACTOR,
    WEEKLY_GROWTH_CAP,
)
from app.planner import paces as paces_mod
from app.planner.paces import PaceTable
from app.planner.phases import (
    DEFAULT_PATTERN,
    DAY_NAMES,
    Phase,
    SessionSlot,
    SessionType,
    phase_sequence,
    slots_for,
)

ENGINE_VERSION = "1.1.0"


class PlanTooShort(ValueError):
    """Not enough runway between today and the race to build anything useful."""


@dataclass(frozen=True)
class FitnessSnapshot:
    reference_distance_m: float
    reference_duration_s: int
    longest_run_m: float
    weekly_km_2wk: float
    weekly_km_4wk: float


@dataclass
class GeneratedSession:
    week_no: int
    day_of_week: int
    date: date
    session_type: str
    target_distance_m: float | None
    target_pace_low: float | None
    target_pace_high: float | None
    structure: dict | None
    notes: str
    label: str = ""
    is_fixed: bool = False


@dataclass
class GeneratedWeek:
    week_no: int
    phase: str
    start: date
    end: date
    target_km: float
    long_run_m: float
    is_down_week: bool
    sessions: list[GeneratedSession] = field(default_factory=list)


@dataclass
class GeneratedPlan:
    start_date: date
    race_date: date
    weeks: int
    goal_distance_m: float
    goal_time_s: int
    engine_version: str
    pace_table: PaceTable
    compressed: bool
    peak_weekly_km: float
    peak_long_run_m: float
    warnings: list[str] = field(default_factory=list)
    week_plans: list[GeneratedWeek] = field(default_factory=list)

    @property
    def total_km(self) -> float:
        return sum(w.target_km for w in self.week_plans)


def _monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def plan_window(
    today: date, race_date: date, *, start_this_week: bool = False
) -> tuple[date, int]:
    """The Monday the plan starts, and how many whole weeks it spans.

    `start_this_week` anchors to the Monday just gone rather than the next one,
    which recovers a whole week of training when the athlete is ready to start
    immediately. Sessions already in the past are simply days the reconciler
    matches or marks missed — no special casing needed.
    """
    anchor = _monday_of(today) if start_this_week else _monday_of(today + timedelta(days=7))
    days = (race_date - anchor).days + 1
    return anchor, days // 7


def starting_weekly_km(fitness: FitnessSnapshot) -> float:
    """Where the volume ramp begins.

    Takes the larger of the two rolling averages. The 4-week figure is the more
    conservative one in general, but it spans this athlete's 11-day gap and so
    describes an interruption rather than a capacity.
    """
    return max(fitness.weekly_km_2wk, fitness.weekly_km_4wk, MIN_START_WEEKLY_KM)


def generate(
    *,
    fitness: FitnessSnapshot,
    goal_distance_m: float,
    goal_time_s: int,
    race_date: date,
    today: date | None = None,
    sessions_per_week: int = 4,
    pattern: list[SessionSlot] | None = None,
    start_this_week: bool = False,
) -> GeneratedPlan:
    today = today or date.today()
    pattern = pattern or DEFAULT_PATTERN
    start, weeks = plan_window(today, race_date, start_this_week=start_this_week)

    if weeks < MIN_PLAN_WEEKS:
        raise PlanTooShort(
            f"{weeks} whole weeks to {race_date} — the engine needs at least "
            f"{MIN_PLAN_WEEKS} to fit a long-run progression and a taper."
        )

    table = paces_mod.derive(
        reference_distance_m=fitness.reference_distance_m,
        reference_duration_s=fitness.reference_duration_s,
        goal_distance_m=goal_distance_m,
        goal_time_s=goal_time_s,
    )

    warnings: list[str] = []
    compressed = weeks <= COMPRESSED_PLAN_WEEKS
    if compressed:
        warnings.append(
            f"Compressed build: {weeks} weeks. No base phase and a one-week taper — "
            f"there is only room to raise the long run and sharpen, not to build "
            f"aerobic base first."
        )
    if table.goal_is_beyond_threshold:
        warnings.append(
            "Goal pace is faster than current threshold pace. The limiter is "
            "speed, not endurance, and this plan cannot close that gap."
        )
    _warn_about_ordering(pattern, warnings)

    phases = phase_sequence(weeks)
    use_down_weeks = weeks > COMPRESSED_PLAN_WEEKS

    base_volume = starting_weekly_km(fitness)
    long_run = fitness.longest_run_m
    peak_volume = base_volume
    peak_long = long_run
    previous_volume = base_volume
    over_cap: list[tuple[int, float]] = []
    short_sessions = False
    long_run_dominates = False

    week_plans: list[GeneratedWeek] = []

    for index, phase in enumerate(phases):
        week_no = index + 1
        is_down = (
            use_down_weeks
            and phase not in (Phase.TAPER, Phase.RACE)
            and week_no % DOWN_WEEK_EVERY == 0
        )

        if phase is Phase.RACE:
            long_run = 0.0
        elif phase is Phase.TAPER:
            long_run = min(peak_long * 0.70, 14000.0)
        elif is_down:
            long_run *= 0.80
        elif week_no == 1:
            # Week one starts where the athlete already is. Stepping up
            # immediately stacks a new long run on top of a volume jump.
            long_run = min(long_run, LONG_RUN_CEILING_M)
        else:
            long_run = min(long_run * (1 + LONG_RUN_STEP_CAP), LONG_RUN_CEILING_M)

        sessions = _build_sessions(
            week_no=week_no,
            phase=phase,
            week_start=start + timedelta(weeks=index),
            long_run_m=long_run,
            goal_distance_m=goal_distance_m,
            table=table,
            pattern=pattern,
            sessions_per_week=sessions_per_week,
        )

        # Volume is what the week actually adds up to.
        training_m = sum(
            s.target_distance_m or 0 for s in sessions if s.session_type != str(SessionType.RACE)
        )
        volume = training_m / 1000.0

        if phase is Phase.TAPER:
            volume = min(volume, peak_volume * TAPER_VOLUME_FACTOR) or volume
        elif phase is Phase.RACE:
            volume = min(volume, peak_volume * RACE_WEEK_VOLUME_FACTOR) or volume
        else:
            growth = volume / previous_volume - 1 if previous_volume else 0.0
            if growth > WEEKLY_GROWTH_CAP + 1e-9:
                over_cap.append((week_no, growth))
            previous_volume = volume
            peak_volume = max(peak_volume, volume)
            peak_long = max(peak_long, long_run)

            if long_run and long_run / max(training_m, 1) > LONG_RUN_WEEK_SHARE:
                long_run_dominates = True

        if any(
            s.target_distance_m
            and s.target_distance_m < MIN_SESSION_DISTANCE_M
            and s.session_type in {"easy", "threshold"}
            for s in sessions
        ):
            short_sessions = True

        week_start = start + timedelta(weeks=index)
        week_plans.append(
            GeneratedWeek(
                week_no=week_no,
                phase=str(phase),
                start=week_start,
                end=week_start + timedelta(days=6),
                target_km=round(volume, 1),
                long_run_m=round(long_run, -1),
                is_down_week=is_down,
                sessions=sessions,
            )
        )

    if over_cap:
        worst = max(g for _, g in over_cap)
        hit = ", ".join(f"W{n}" for n, _ in over_cap)
        warnings.append(
            f"Weekly volume rises faster than the {WEEKLY_GROWTH_CAP:.0%} cap in {hit} "
            f"(peaking at +{worst:.0%}). Four runs a week including a "
            f"{peak_long / 1000:.0f} km long run comes to about {peak_volume:.0f} km, "
            f"and there is not enough runway to reach that gradually. This is the "
            f"plan's main injury risk — if anything aches, cut the easy runs before "
            f"the long run."
        )
    if long_run_dominates:
        warnings.append(
            f"The long run exceeds {LONG_RUN_WEEK_SHARE:.0%} of weekly volume in at "
            f"least one week. That is workable but unbalanced — more weekly volume "
            f"would carry it better."
        )
    if short_sessions:
        warnings.append(
            f"Some sessions fall below {MIN_SESSION_DISTANCE_M / 1000:.0f} km, short "
            f"enough to be worth little."
        )

    return GeneratedPlan(
        start_date=start,
        race_date=race_date,
        weeks=weeks,
        goal_distance_m=goal_distance_m,
        goal_time_s=goal_time_s,
        engine_version=ENGINE_VERSION,
        pace_table=table,
        compressed=compressed,
        peak_weekly_km=round(peak_volume, 1),
        peak_long_run_m=round(peak_long, -1),
        warnings=warnings,
        week_plans=week_plans,
    )


def _warn_about_ordering(pattern: list[SessionSlot], warnings: list[str]) -> None:
    """Flag a hard session sitting immediately before the long run."""
    by_day = {s.day_of_week: s for s in pattern}
    for slot in pattern:
        if slot.session_type is not SessionType.LONG:
            continue
        before = by_day.get(slot.day_of_week - 1)
        if before is not None and before.session_type is SessionType.THRESHOLD:
            warnings.append(
                f"{DAY_NAMES[before.day_of_week]}'s threshold session sits directly "
                f"before {DAY_NAMES[slot.day_of_week]}'s long run. The long run is the "
                f"session that moves the goal, and it would be run on tired legs. "
                f"Move the quality day midweek."
            )


def _build_sessions(
    *,
    week_no: int,
    phase: Phase,
    week_start: date,
    long_run_m: float,
    goal_distance_m: float,
    table: PaceTable,
    pattern: list[SessionSlot],
    sessions_per_week: int,
) -> list[GeneratedSession]:
    slots = slots_for(phase, pattern)[:sessions_per_week]
    out: list[GeneratedSession] = []

    for slot in slots:
        if slot.session_type is SessionType.LONG:
            distance = long_run_m
            band = table.long
        elif slot.session_type is SessionType.RACE:
            distance = goal_distance_m
            band = table.goal
        elif slot.is_fixed:
            distance = slot.fixed_distance_m or 0.0
            band = table.threshold if slot.session_type is SessionType.THRESHOLD else table.easy
        else:
            # Flexible sessions scale with the week's long run, so support
            # volume grows alongside the session that is actually progressing.
            distance = max(long_run_m * slot.long_run_fraction, MIN_SESSION_DISTANCE_M)
            band = table.threshold if slot.session_type is SessionType.THRESHOLD else table.easy

        low, high = band.low, band.high
        if slot.fixed_pace_s:
            low = high = slot.fixed_pace_s

        out.append(
            GeneratedSession(
                week_no=week_no,
                day_of_week=slot.day_of_week,
                date=week_start + timedelta(days=slot.day_of_week),
                session_type=str(slot.session_type),
                target_distance_m=round(distance, -1) if distance else None,
                target_pace_low=round(low, 1),
                target_pace_high=round(high, 1),
                structure=slot.structure,
                notes=slot.notes,
                label=slot.label,
                is_fixed=slot.is_fixed,
            )
        )

    return sorted(out, key=lambda s: s.day_of_week)
