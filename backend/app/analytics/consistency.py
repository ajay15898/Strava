"""Volume rollups, frequency and gap analysis.

Consistency rather than speed is this athlete's limiter, so gaps are a
first-class output, not a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.analytics.base import run_days, total_km
from app.constants import CONSISTENCY_GAP_DAYS
from app.models import Activity


@dataclass
class Gap:
    start: date
    end: date
    days: int


@dataclass
class WeekSummary:
    start: date
    end: date
    km: float
    run_days: int


@dataclass
class MonthSummary:
    year: int
    month: int
    km: float
    run_days: int
    span_days: int

    @property
    def km_per_week(self) -> float:
        return self.km / (self.span_days / 7) if self.span_days else 0.0


@dataclass
class ConsistencyReport:
    window_start: date
    window_end: date
    total_km: float
    total_run_days: int
    km_per_week_overall: float
    km_per_week_2wk: float
    km_per_week_4wk: float
    longest_gap_days: int
    gaps: list[Gap] = field(default_factory=list)
    weeks: list[WeekSummary] = field(default_factory=list)
    months: list[MonthSummary] = field(default_factory=list)


def window_km(runs: list[Activity], end: date, days: int) -> float:
    start = end - timedelta(days=days - 1)
    return total_km([r for r in runs if start <= r.start_local.date() <= end])


def find_gaps(runs: list[Activity], min_days: int = CONSISTENCY_GAP_DAYS) -> list[Gap]:
    """Gaps between consecutive run days at or above the threshold."""
    days = sorted(run_days(runs))
    gaps = []
    for a, b in zip(days, days[1:]):
        delta = (b - a).days
        if delta >= min_days:
            gaps.append(Gap(start=a, end=b, days=delta))
    return gaps


def weekly_summaries(runs: list[Activity], end: date, weeks: int) -> list[WeekSummary]:
    out = []
    for w in range(weeks - 1, -1, -1):
        hi = end - timedelta(days=7 * w)
        lo = hi - timedelta(days=6)
        in_week = [r for r in runs if lo <= r.start_local.date() <= hi]
        out.append(
            WeekSummary(start=lo, end=hi, km=total_km(in_week), run_days=len(run_days(in_week)))
        )
    return out


def monthly_summaries(runs: list[Activity], start: date, end: date) -> list[MonthSummary]:
    """Calendar months, with spans clipped to the requested window.

    Clipping matters: a partial first or last month would otherwise report a
    misleading km/week.
    """
    out: list[MonthSummary] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        nxt = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)
        lo, hi = max(cursor, start), min(nxt - timedelta(days=1), end)
        in_month = [r for r in runs if lo <= r.start_local.date() <= hi]
        out.append(
            MonthSummary(
                year=cursor.year,
                month=cursor.month,
                km=total_km(in_month),
                run_days=len(run_days(in_month)),
                span_days=(hi - lo).days + 1,
            )
        )
        cursor = nxt
    return out


def build_report(runs: list[Activity], start: date, end: date) -> ConsistencyReport:
    gaps = find_gaps(runs)
    span_weeks = ((end - start).days + 1) / 7
    km = total_km(runs)
    return ConsistencyReport(
        window_start=start,
        window_end=end,
        total_km=round(km, 2),
        total_run_days=len(run_days(runs)),
        km_per_week_overall=round(km / span_weeks, 2) if span_weeks else 0.0,
        km_per_week_2wk=round(window_km(runs, end, 14) / 2, 2),
        km_per_week_4wk=round(window_km(runs, end, 28) / 4, 2),
        longest_gap_days=max((g.days for g in gaps), default=0),
        gaps=gaps,
        weeks=weekly_summaries(runs, end, 8),
        months=monthly_summaries(runs, start, end),
    )
