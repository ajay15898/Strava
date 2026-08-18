/** Mirrors backend/app/schemas/responses.py. */

export interface Activity {
  id: number;
  strava_id: number;
  name: string | null;
  sport_type: string;
  start_local: string;
  distance_m: number;
  moving_time_s: number;
  elapsed_time_s: number;
  elevation_gain_m: number | null;
  avg_speed: number | null;
  avg_hr: number | null;
  has_heartrate: boolean;
  avg_watts: number | null;
  calories: number | null;
  is_duplicate: boolean;
  duplicate_of_strava_id: number | null;
}

export interface Gap {
  start: string;
  end: string;
  days: number;
}

export interface Week {
  start: string;
  end: string;
  km: number;
  run_days: number;
}

export interface Month {
  year: number;
  month: number;
  km: number;
  run_days: number;
  span_days: number;
  km_per_week: number;
}

export interface Summary {
  window_start: string;
  window_end: string;
  total_km: number;
  total_run_days: number;
  km_per_week_overall: number;
  km_per_week_2wk: number;
  km_per_week_4wk: number;
  longest_gap_days: number;
  gaps: Gap[];
  weeks: Week[];
  months: Month[];
  has_recent_heartrate: boolean;
  last_heartrate_date: string | null;
}

export interface LoadDay {
  date: string;
  load: number;
  ctl: number;
  atl: number;
  tsb: number;
}

export interface PacePoint {
  distance_m: number;
  duration_s: number;
  duration_display: string | null;
  pace_s_per_km: number;
  activity_id: number;
  activity_date: string;
  effort_type: string;
  is_maximal: boolean;
}

export interface Prediction {
  target_distance_m: number;
  reference_distance_m: number;
  reference_duration_s: number;
  reference_duration_display: string | null;
  reference_date: string;
  reference_effort_type: string;
  used_maximal_reference: boolean;
  riegel_s: number;
  cameron_s: number;
  blended_s: number;
  durability_ratio: number;
  durability_penalty_pct: number;
  predicted_time_s: number;
  predicted_time_display: string | null;
  predicted_pace_s_per_km: number;
  notes: string[];
}

export type Verdict = "on_track" | "tight" | "unrealistic";

export interface Feasibility {
  verdict: Verdict;
  predicted_time_s: number;
  predicted_time_display: string | null;
  required_weekly_peak_km: number;
  current_weekly_km: number;
  limiting_factor: string;
}

export interface AthleteProfile {
  id: number;
  strava_id: number;
  name: string | null;
  measurement_pref: string;
  goal_race_distance_m: number | null;
  goal_time_s: number | null;
  goal_race_date: string | null;
  max_sessions_per_week: number | null;
}

export type SessionStatus = "planned" | "done" | "missed" | "moved";

export interface PlanSession {
  id: number;
  week_no: number;
  day_of_week: number;
  date: string;
  session_type: string;
  target_distance_m: number | null;
  target_pace_low: number | null;
  target_pace_high: number | null;
  structure: Record<string, unknown> | null;
  notes: string | null;
  status: SessionStatus;
  matched_activity_id: number | null;
}

export interface PlanWeek {
  week_no: number;
  start: string;
  end: string;
  target_km: number;
  race_km: number;
  long_run_m: number;
  sessions: PlanSession[];
}

export interface PlanMeta {
  compressed: boolean;
  warnings: string[];
  peak_weekly_km: number;
  peak_long_run_m: number;
  total_km: number;
  reference: { distance_m: number; duration_s: number };
  paces: Record<string, { low: number; high: number }>;
}

export interface PlanDetail {
  id: number;
  athlete_id: number;
  goal_time_s: number;
  goal_time_display: string | null;
  race_date: string;
  start_date: string;
  weeks: number;
  engine_version: string;
  meta: PlanMeta | null;
  weeks_detail: PlanWeek[];
  compliance: Record<string, number>;
}

export type AdaptationSeverity = "info" | "warning" | "action";

export interface Adaptation {
  rule: string;
  severity: AdaptationSeverity;
  action: string;
  message: string;
  data: Record<string, unknown>;
}

export interface Digest {
  week_no: number;
  week_start: string;
  planned_km: number;
  actual_km: number;
  completion: number;
  sessions_done: number;
  sessions_total: number;
  adaptations: Adaptation[];
}

export interface CoachReply {
  content: string;
  verified: boolean;
  used_fallback: boolean;
  attempts: number;
  violations: string[];
  model: string;
}

export interface CoachMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}
