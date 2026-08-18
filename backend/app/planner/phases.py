"""Phase templates and the weekly session pattern.

The pattern is athlete configuration, not engine preference. Some sessions are
fixed commitments — a club threshold night, a Sunday social run — that the
engine must plan *around* rather than size. Others it is free to scale.

Ordering matters more than it looks. A threshold session the day before the
long run means the one session that actually moves this athlete's projection
gets run on tired legs; an easy run the day *after* it is a durability builder
rather than a cost. So quality sits midweek and the weekend is long run then
easy.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class Phase(StrEnum):
    BASE = "base"
    BUILD = "build"
    PEAK = "peak"
    TAPER = "taper"
    RACE = "race"


class SessionType(StrEnum):
    EASY = "easy"
    LONG = "long"
    THRESHOLD = "threshold"
    SHAKEOUT = "shakeout"
    RACE = "race"
    REST = "rest"


# Monday = 0 … Sunday = 6
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class SessionSlot:
    day_of_week: int
    session_type: SessionType
    #: A standing commitment the engine may not resize.
    fixed_distance_m: float | None = None
    #: A pace the athlete runs this session at regardless of prescription.
    fixed_pace_s: float | None = None
    #: Flexible sessions are sized as this multiple of the week's long run.
    long_run_fraction: float = 0.30
    label: str = ""
    structure: dict | None = None
    notes: str = ""

    @property
    def is_fixed(self) -> bool:
        return self.fixed_distance_m is not None


def threshold_structure(reps: int, minutes: int) -> dict:
    return {
        "warmup_min": 12,
        "reps": reps,
        "rep_minutes": minutes,
        "recovery_min": 2,
        "cooldown_min": 10,
    }


#: Quality midweek, long run Saturday, easy social Sunday on tired legs.
DEFAULT_PATTERN: list[SessionSlot] = [
    SessionSlot(
        TUE,
        SessionType.EASY,
        long_run_fraction=0.28,
        notes="Conversational. Slower than it feels.",
    ),
    SessionSlot(
        WED,
        SessionType.THRESHOLD,
        structure=threshold_structure(3, 8),
        notes="Comfortably hard — controlled, not a race.",
    ),
    SessionSlot(
        SAT,
        SessionType.LONG,
        notes="Time on feet. This is the session that moves the goal.",
    ),
    SessionSlot(
        SUN,
        SessionType.EASY,
        label="Social run",
        notes="On yesterday's legs — running tired is the point, keep it easy.",
    ),
]

RACE_WEEK: list[SessionSlot] = [
    SessionSlot(TUE, SessionType.EASY, fixed_distance_m=5000.0, notes="Short and easy."),
    SessionSlot(
        THU,
        SessionType.SHAKEOUT,
        fixed_distance_m=4000.0,
        structure={"strides": 4, "stride_seconds": 20},
        notes="Easy with 4 × 20 s strides to stay sharp.",
    ),
    SessionSlot(SUN, SessionType.RACE, notes="Race day. Go out at goal pace, not faster."),
]


def pattern_from_config(config: list[dict[str, Any]] | None) -> list[SessionSlot]:
    """Build a week pattern from stored athlete preferences."""
    if not config:
        return DEFAULT_PATTERN

    out: list[SessionSlot] = []
    for entry in config:
        out.append(
            SessionSlot(
                day_of_week=int(entry["day"]),
                session_type=SessionType(entry.get("type", "easy")),
                fixed_distance_m=entry.get("fixed_distance_m"),
                fixed_pace_s=entry.get("fixed_pace_s"),
                long_run_fraction=float(entry.get("long_run_fraction", 0.30)),
                label=entry.get("label", ""),
                structure=entry.get("structure"),
                notes=entry.get("notes", ""),
            )
        )
    return sorted(out, key=lambda s: s.day_of_week)


def taper_variant(pattern: list[SessionSlot]) -> list[SessionSlot]:
    """Taper keeps the shape and the intensity, and cuts the volume."""
    out: list[SessionSlot] = []
    for slot in pattern:
        if slot.session_type is SessionType.THRESHOLD:
            out.append(
                replace(
                    slot,
                    structure=threshold_structure(2, 6),
                    fixed_distance_m=(slot.fixed_distance_m or 0) * 0.75 or None,
                    notes="Intensity held, volume cut. Sharpening, not training.",
                )
            )
        elif slot.session_type is SessionType.LONG:
            out.append(replace(slot, notes="Last long run. Comfortable throughout."))
        else:
            out.append(
                replace(
                    slot,
                    fixed_distance_m=(slot.fixed_distance_m or 0) * 0.75 or None,
                    long_run_fraction=slot.long_run_fraction * 0.85,
                )
            )
    return out


@dataclass
class WeekPlan:
    week_no: int
    phase: Phase
    slots: list[SessionSlot] = field(default_factory=list)
    is_down_week: bool = False


def phase_sequence(total_weeks: int) -> list[Phase]:
    """Lay phases over the available weeks.

    A compressed plan drops the base phase first and shortens the taper to a
    single week — with six or seven weeks there is no room to build aerobic
    base and still get the long run up, and the long run decides this race.
    """
    if total_weeks <= 8:
        return [Phase.BUILD] * (total_weeks - 2) + [Phase.TAPER, Phase.RACE]

    if total_weeks <= 11:
        build = total_weeks - 5
        return [Phase.BASE] * 2 + [Phase.BUILD] * build + [Phase.PEAK] + [Phase.TAPER, Phase.RACE]

    base = max(3, round(total_weeks * 0.28))
    peak = 3
    build = total_weeks - base - peak - 2
    return (
        [Phase.BASE] * base
        + [Phase.BUILD] * build
        + [Phase.PEAK] * peak
        + [Phase.TAPER, Phase.RACE]
    )


def slots_for(phase: Phase, pattern: list[SessionSlot]) -> list[SessionSlot]:
    if phase is Phase.RACE:
        return RACE_WEEK
    if phase is Phase.TAPER:
        return taper_variant(pattern)
    return pattern
