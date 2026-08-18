"""Every tunable threshold in the ingest and analytics layers.

Nothing here is model judgement. The coach may quote these values; it may not
change them. Each constant records why it holds the value it does, because the
numbers were chosen against real history rather than picked off a blog post.
"""

# --- Deduplication -------------------------------------------------------
# Two devices logging the same run. Observed gaps in the 2026 history were
# 6 s, 6 s and 112 s. A 120 s window would have cleared the widest real pair by
# only 8 s, so it is widened here: the same-sport and distance guards do the
# discriminating work, and two *distinct* runs starting within five minutes of
# each other AND landing within 5% on distance is not a real training pattern.
# Verified against 2026-03-17, which has two genuine runs 23 min apart
# (5173 m and 1638 m) — separated correctly by the distance guard alone.
DUPLICATE_WINDOW_S = 300
DUPLICATE_DISTANCE_TOLERANCE = 0.05

# --- Noise floor ---------------------------------------------------------
# 2026-03-18 contains a 19.2 m "run" lasting 237 s — a watch started and
# abandoned. Excluded from every analytic, including run-day counting: a
# phantom training day corrupts consistency metrics as badly as a phantom
# kilometre corrupts volume. Rows are kept in the table, never hard-deleted.
NOISE_FLOOR_M = 500.0

# Sport types that count as running for analytics purposes.
RUN_SPORT_TYPES = frozenset({"Run", "TrailRun", "VirtualRun"})

# --- Training load (rTSS) ------------------------------------------------
# No heart rate is present on recent activities, so load is derived from pace
# against threshold pace rather than from HR. Equivalent to running TSS:
#   load = (duration_h) * IF^2 * 100,  IF = actual_speed / threshold_speed
# Threshold speed is the Z4 lower bound from Strava run_zones (3.207 m/s,
# ~5:12/km), which is the athlete's current threshold pace.
DEFAULT_THRESHOLD_SPEED_MS = 3.207

# Exponential time constants for the fitness/fatigue model.
CTL_DAYS = 42
ATL_DAYS = 7

# --- Race prediction -----------------------------------------------------
# Riegel's exponent. 1.06 is the classic value and assumes the athlete is
# equally trained across the whole range. That assumption does not hold for a
# 21.1 km goal off a 15 km longest run, which is why DURABILITY_* exists below.
RIEGEL_EXPONENT = 1.06

# Durability penalty. Riegel and Cameron both extrapolate pure speed; neither
# knows whether the athlete has ever run the distance. Below a longest-run to
# race-distance ratio of DURABILITY_FULL_RATIO the prediction is inflated
# proportionally to the shortfall.
#   penalty = (FULL_RATIO - ratio) * K,  clamped at >= 0
# At the 2026-08-16 baseline (15.01 km longest, 21.10 km race) ratio is 0.711,
# giving a 4.2% penalty. Calibration note: K was chosen so that an athlete who
# has never run past half the race distance carries roughly a 10% penalty.
DURABILITY_FULL_RATIO = 0.85
DURABILITY_K = 0.30
DURABILITY_MAX_PENALTY = 0.15

# --- Consistency ---------------------------------------------------------
# Gaps at or above this length are the failure mode in this athlete's history;
# every fitness regression in the 2026 data follows one.
CONSISTENCY_GAP_DAYS = 7

# --- Feasibility ---------------------------------------------------------
# Verdict boundaries, expressed as predicted_time / goal_time.
FEASIBILITY_ON_TRACK = 0.98
FEASIBILITY_TIGHT = 1.06

# Weekly volume a half-marathon build is expected to peak at, in km.
HM_PEAK_WEEKLY_KM = 45.0

# --- Standard race distances (m) ----------------------------------------
HALF_MARATHON_M = 21097.5
MARATHON_M = 42195.0


# =========================================================================
# Planner
# =========================================================================

# Minimum runway the engine will plan for. The original spec said 8 weeks.
# Lowered to 6 for the 2026-10-04 race, deliberately and with the compression
# surfaced on the plan rather than hidden: modelling the actual six-week block
# showed the goal is still reachable, because what moves this athlete's
# projection is long-run distance, not weekly mileage — and 15.01 km to the
# 17.93 km penalty-free threshold is only three steps inside the step cap.
# Below 6 weeks there is not enough room for even one long-run progression
# plus a taper, so the refusal stands.
MIN_PLAN_WEEKS = 6
COMPRESSED_PLAN_WEEKS = 8  # at or below this, the plan is flagged as compressed

# Starting weekly volume. The 4-week average is the headline figure, but it
# spans an 11-day gap for this athlete and so understates what they have
# actually demonstrated — the 2-week average is taken when it is higher, and a
# 20 km floor applies to both.
MIN_START_WEEKLY_KM = 20.0

# Volume progression.
WEEKLY_GROWTH_CAP = 0.08
DOWN_WEEK_EVERY = 4
DOWN_WEEK_FACTOR = 0.75

# Long-run progression. The step cap is the injury guard; the ceiling reflects
# that running the full race distance in training costs more recovery than it
# returns for a half marathon.
LONG_RUN_STEP_CAP = 0.15
LONG_RUN_CEILING_M = 20000.0

# Taper. The race-week factor covers *training* volume only — the race
# itself is not counted against it.
TAPER_VOLUME_FACTOR = 0.70
RACE_WEEK_VOLUME_FACTOR = 0.25

# The long run's share of the week. This is not a limit applied after the
# fact — it is what *derives* weekly volume from the long run, because for
# this athlete the long run is the driver and total mileage follows it.
# At 0.70 the remaining three sessions came out at 2-3 km each, which is
# not a training stimulus; 0.55 leaves a threshold session long enough to
# hold its reps plus a warm-up.
LONG_RUN_WEEK_SHARE = 0.55

# Below this, a prescribed run is not worth the shoe change.
MIN_SESSION_DISTANCE_M = 4000.0

# --- Pace derivation -----------------------------------------------------
# Multipliers applied to current 5 K race pace. Chosen to land on the bands a
# coach would prescribe, and cross-checked against this athlete's own Strava
# run_zones: derived threshold 5:22/km sits inside the Z3/Z4 boundary of
# 5:12-5:47, and derived easy 6:35-7:05/km sits in Z1/Z2 as it should.
PACE_MULTIPLIERS: dict[str, tuple[float, float]] = {
    "recovery": (1.40, 1.52),
    "easy": (1.30, 1.40),
    "long": (1.25, 1.35),
    "threshold": (1.04, 1.08),
    "interval": (0.985, 1.02),
    "strides": (0.84, 0.90),
}


# =========================================================================
# Adaptation (M6)
# =========================================================================
# Thresholds, not judgement. The coach may quote these; it may not change
# them, and nothing here is decided by a model.

# One missed session in a week is absorbed silently — insisting on a perfect
# week is how a plan gets abandoned. Two is a signal.
MISSED_ABSORB_LIMIT = 1
MISSED_REPEAT_WEEK = 2

# The failure mode in this athlete's history: every fitness regression in the
# 2026 data follows a gap of this length or longer.
LAYOFF_REBUILD_DAYS = 7

# After a layoff, the peak target is pulled back by this much before rebuilding.
LAYOFF_PEAK_REDUCTION = 0.10

# A long run this far under target means the next step up has not been earned.
LONG_RUN_SHORTFALL = 0.20

# Easy runs faster than the easy band's ceiling, this many in a row, means the
# athlete is not running easy — the most common self-inflicted training error.
EASY_PACE_STREAK = 3

# Chronic fatigue. Below this, a recovery day is inserted rather than suggested.
TSB_FORCE_RECOVERY = -30.0

# Goal-pace work held at target this many weeks running earns a faster target.
GOAL_PACE_ADVANCE_WEEKS = 3
GOAL_PACE_ADVANCE_S = 5.0

# --- Background sync -----------------------------------------------------
# Strava's read budget is 100 per 15 min / 1000 per day. An incremental sync
# costs one list call plus detail for anything new, so this interval is far
# inside the cap while keeping the dashboard close to live.
SYNC_INTERVAL_MINUTES = 20
