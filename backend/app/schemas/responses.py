from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


def fmt_duration(seconds: float | None) -> str | None:
    """Seconds to h:mm:ss or m:ss — the only numeric formatting the coach's
    verifier is permitted to treat as a derived form."""
    if seconds is None:
        return None
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strava_id: int
    name: str | None
    sport_type: str
    start_local: datetime
    distance_m: float
    moving_time_s: int
    elapsed_time_s: int
    elevation_gain_m: float | None
    avg_speed: float | None
    avg_hr: float | None
    has_heartrate: bool
    avg_watts: float | None
    calories: float | None
    is_duplicate: bool
    duplicate_of_strava_id: int | None

    @property
    def pace_s_per_km(self) -> float | None:
        if self.distance_m <= 0 or self.moving_time_s <= 0:
            return None
        return self.moving_time_s / (self.distance_m / 1000.0)


class GapOut(BaseModel):
    start: date
    end: date
    days: int


class WeekOut(BaseModel):
    start: date
    end: date
    km: float
    run_days: int


class MonthOut(BaseModel):
    year: int
    month: int
    km: float
    run_days: int
    span_days: int
    km_per_week: float


class SummaryOut(BaseModel):
    window_start: date
    window_end: date
    total_km: float
    total_run_days: int
    km_per_week_overall: float
    km_per_week_2wk: float
    km_per_week_4wk: float
    longest_gap_days: int
    gaps: list[GapOut]
    weeks: list[WeekOut]
    months: list[MonthOut]
    has_recent_heartrate: bool
    last_heartrate_date: date | None


class LoadDayOut(BaseModel):
    date: date
    load: float
    ctl: float
    atl: float
    tsb: float


class PacePointOut(BaseModel):
    distance_m: float
    duration_s: int
    duration_display: str | None
    pace_s_per_km: float
    activity_id: int
    activity_date: date
    effort_type: str
    is_maximal: bool


class PredictionOut(BaseModel):
    target_distance_m: float
    reference_distance_m: float
    reference_duration_s: int
    reference_duration_display: str | None
    reference_date: date
    reference_effort_type: str
    used_maximal_reference: bool
    riegel_s: int
    cameron_s: int
    blended_s: int
    durability_ratio: float
    durability_penalty_pct: float
    #: The number the durability ratio is built from. Omitting it left
    #: consumers unable to explain the penalty without recomputing it.
    longest_run_m: float
    predicted_time_s: int
    predicted_time_display: str | None
    predicted_pace_s_per_km: float
    notes: list[str]


class FeasibilityOut(BaseModel):
    verdict: str
    predicted_time_s: int
    predicted_time_display: str | None
    required_weekly_peak_km: float
    current_weekly_km: float
    limiting_factor: str


class SyncResultOut(BaseModel):
    imported: int
    duplicates: int
    details: int
