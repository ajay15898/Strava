"""Within-run analysis: aerobic decoupling and split fade.

Decoupling is the reason M7 exists. It asks a question no single-number summary
can: did the athlete hold the same output for the same effort all the way
through, or did they drift? A run that starts at 6:20/km at 150 bpm and ends at
6:20/km at 165 bpm was not the same run twice.

Two variants, because this athlete's data has an unusual shape:

- **Pw:HR** — power against heart rate. The device records real running power
  on every activity, so once heart rate arrives this is the better signal.
- **Pa:HR** — pace against heart rate. The conventional form, kept as a
  fallback for activities without power.

Both need heart rate. Until it appears, `decoupling` returns `None` with a
reason attached rather than a fabricated zero — a missing measurement and a
good measurement must never look alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

#: Below this many samples a half is too short to mean anything.
MIN_SAMPLES_PER_HALF = 30

#: Conventional threshold. Above this, aerobic durability is the limiter.
DECOUPLING_CONCERN_PCT = 5.0


@dataclass
class Decoupling:
    """Drift between the first and second half of a run."""

    pct: float | None
    method: str  # pw:hr | pa:hr | none
    first_half_ratio: float | None = None
    second_half_ratio: float | None = None
    reason: str | None = None

    @property
    def is_concerning(self) -> bool:
        return self.pct is not None and self.pct > DECOUPLING_CONCERN_PCT


def _clean_halves(
    output: list[float], heart_rate: list[float], moving: list[bool] | None
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]] | None:
    """Pair output with HR, drop stopped/invalid samples, split in two."""
    paired = [
        (o, h)
        for i, (o, h) in enumerate(zip(output, heart_rate))
        if o and h and o > 0 and h > 0 and (moving is None or i >= len(moving) or moving[i])
    ]
    if len(paired) < MIN_SAMPLES_PER_HALF * 2:
        return None

    mid = len(paired) // 2
    return paired[:mid], paired[mid:]


def decoupling(
    *,
    heart_rate: list[float] | None,
    watts: list[float] | None = None,
    velocity: list[float] | None = None,
    moving: list[bool] | None = None,
) -> Decoupling:
    """Percentage drift in output-per-heartbeat between the two halves.

    Positive means the second half cost more heartbeats for the same output —
    the athlete faded. Negative means they held or improved.
    """
    if not heart_rate or not any(heart_rate):
        return Decoupling(
            pct=None,
            method="none",
            reason="No heart-rate stream on this activity.",
        )

    output, method = (watts, "pw:hr") if watts and any(watts) else (velocity, "pa:hr")
    if not output or not any(output):
        return Decoupling(
            pct=None, method="none", reason="No power or velocity stream on this activity."
        )

    halves = _clean_halves(output, heart_rate, moving)
    if halves is None:
        return Decoupling(
            pct=None,
            method=method,
            reason=f"Fewer than {MIN_SAMPLES_PER_HALF * 2} usable samples.",
        )

    first, second = halves
    first_ratio = fmean(o / h for o, h in first)
    second_ratio = fmean(o / h for o, h in second)
    if first_ratio == 0:
        return Decoupling(pct=None, method=method, reason="First half ratio was zero.")

    drift = (first_ratio - second_ratio) / first_ratio * 100
    return Decoupling(
        pct=round(drift, 2),
        method=method,
        first_half_ratio=round(first_ratio, 4),
        second_half_ratio=round(second_ratio, 4),
    )


@dataclass
class SplitFade:
    """How much the athlete slowed across a run, split by split."""

    first_km_pace_s: float | None
    last_km_pace_s: float | None
    fade_pct: float | None
    fastest_km: int | None
    slowest_km: int | None
    negative_split: bool | None


def split_fade(paces_s_per_km: list[float]) -> SplitFade:
    """Fade across whole kilometres.

    The final split is excluded when it is short — a run ending at 5.2 km has a
    200 m 'kilometre' whose pace is noise, and letting it define the finish
    would make every run look like a collapse or a sprint.
    """
    usable = [p for p in paces_s_per_km if p and p > 0]
    if len(usable) < 2:
        return SplitFade(None, None, None, None, None, None)

    first, last = usable[0], usable[-1]
    fade = (last - first) / first * 100

    mid = len(usable) // 2
    first_half = fmean(usable[:mid])
    second_half = fmean(usable[mid:])

    return SplitFade(
        first_km_pace_s=round(first, 1),
        last_km_pace_s=round(last, 1),
        fade_pct=round(fade, 2),
        fastest_km=usable.index(min(usable)) + 1,
        slowest_km=usable.index(max(usable)) + 1,
        negative_split=second_half < first_half,
    )
