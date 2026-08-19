# Design notes

Why the engine works the way it does. Most of these decisions were forced by
real data rather than chosen in the abstract, and several of them corrected an
earlier version that looked reasonable and was wrong.

---

## Ingest

### Deduplication

Two devices recording the same run produce two activities seconds apart. Left
alone they inflate every volume metric — in the history this was built against,
by 5.9%.

Rule: same sport type, start within 300 s, distance within 5% → keep the record
with more populated fields, flag the other. Never hard-deleted, so volume can be
audited with and without duplicates.

The window is 300 s rather than the more obvious 120 s because a real duplicate
pair in the source data was 112 s apart — eight seconds of margin. The
same-sport and distance guards do the discriminating work; two *distinct* runs
starting within five minutes of each other **and** landing within 5% on distance
is not a real training pattern. Verified against a day holding two genuine runs
23 minutes apart, which the distance guard separates cleanly.

Tie-break is completeness, not distance. A device that logged heart rate,
calories and power is more useful than one that logged 70 m more.

### Noise floor

Activities under 500 m are excluded from every analytic — including run-day
counting. A 19 m "run" lasting 237 s exists in the source history: a watch
started and abandoned. Filtering it from distance but counting it as a training
day corrupts consistency metrics just as badly.

`analytics/base.py` defines "an analysable run" exactly once so distance and
day-counting cannot diverge.

### Rate limits are read, not assumed

The app's actual read budget was **100 per 15 min / 1000 per day** — an order of
magnitude below the 600/30,000 figures that circulate in older documentation. A
hardcoded limiter would have sailed past the real cap. `strava/client.py` parses
`X-ReadRateLimit-*` off every response and pauses before crossing it.

A full activity backfill costs ~50 requests. A stream backfill would cost one
per activity, which is why streams are fetched lazily.

### Best efforts are free

Strava returns per-activity best efforts (400 m through 30 K) on the detail
payload, so the pace-at-distance curve needs no stream data at all. That moves
it out of the streams milestone entirely.

Note that the REST API names them `5K`, `10K`, `1K` while some wrappers return
`Fastest5k`. Both spellings are mapped; handling only one silently produces an
empty curve.

---

## Prediction

### Seed from best efforts, never from activity moving time

The original spec recorded a "24:57 5K" that was actually `moving_time` over
**4992.59 m** — seven metres short, on the more generous clock. The real
`Fastest5k` for that activity was 25:18.

A 21-second error in the seed moved the half-marathon projection by about 90
seconds, which was the difference between "on track" and "tight". Predictions
read `best_effort` rows.

### The durability penalty

Riegel and Cameron both extrapolate pure speed. Neither knows whether the
athlete has ever run the distance. With a longest run at 0.71 of race distance,
the final third is unrehearsed — precisely the regime where speed extrapolation
over-predicts.

```
penalty = (0.85 - longest_run/race_distance) * 0.30,  clamped to [0, 0.15]
```

`DURABILITY_K = 0.30` is reasoned, not fitted: chosen so an athlete who has
never run past half the race distance carries roughly a 10% penalty. One
completed race would let it be calibrated against reality.

The two formulae agree within about 1% over 5 K → half marathon, so the choice
of formula is not what decides the verdict. Durability is.

### Reference effort selection

The predictor picks the effort implying the fastest target time, among efforts
at least 20% of the target distance.

This sidesteps detecting whether an effort was *maximal*, which is not reliably
possible without heart rate: a 15 K best effort inside a 15 km easy run spans
nearly the whole activity, so any "was the run as hard as the effort" test says
yes. Ranking by implied performance discards easy efforts automatically, because
an easy 15 K implies a slower race than a hard 5 K does.

The distance floor handles the other failure mode — a sharp 400 m projects a
fantasy half marathon.

Recency matters too. A 10 K personal best four months old projects a time that
badly misdescribes current fitness, so references expire after 90 days.

### Training load without heart rate

Strava's Relative Effort is heart-rate derived. Where no heart rate exists, load
falls back to running TSS from pace against threshold pace:

```
load = duration_h * IF^2 * 100,   IF = avg_speed / threshold_speed
```

Relative Effort is still preferred when supplied, so the series degrades
gracefully rather than switching wholesale between two scales.

---

## Planner

### The long run drives; volume follows

The first implementation sized the week first and capped the long run at 70% of
it. That produced **2–3 km easy runs** — the long run ate everything.

The causality was backwards. For an athlete whose limiter is durability, the
long run progresses on its own capped schedule and the week is sized to carry
it. Fixed commitments keep their distance; flexible sessions scale as a fraction
of that week's long run; weekly volume is the *sum* of the week, not a target
the sessions get fitted into.

`HM_PEAK_WEEKLY_KM` is deliberately not consulted by the engine. It describes a
typical build, not a binding constraint, and nothing in the prediction path
reads it.

### Session ordering

A threshold session the day before the long run means the one session that
actually moves the projection gets run on tired legs. An easy run the day
*after* it is a durability builder rather than a cost.

So quality sits midweek and the weekend is long run then easy.
`_warn_about_ordering` flags the adjacency for any configured pattern rather
than assuming one shape.

The weekly pattern lives in `athlete.preferences` as JSON — training days, and
which sessions are standing commitments the engine must plan *around* rather
than size.

### Paces are derived, not tabulated

Everything is anchored to one measured reference effort via multipliers in
`constants.PACE_MULTIPLIERS`. A hardcoded pace table stops matching the athlete
the moment they get fitter, and — more immediately — it was a hardcoded seed
that carried the 5 K error into every prescribed band.

Goal pace is the exception: arithmetic on the goal, not a derivation from
fitness. If goal pace lands faster than threshold pace, the goal is not a pace
problem, and `PaceTable.goal_is_beyond_threshold` says so.

### Compressed plans

The minimum runway is 6 weeks, lowered from 8. Below 6 there is not enough room
for even one long-run progression plus a taper, so the refusal stands.

A compressed plan reports its costs on the plan rather than burying them: no
base phase, a one-week taper, and — when carrying the required long run implies
weekly growth above the 8% cap — the implied growth rate, named by week.

---

## Adaptation

Six rules, run on every ingest. Every threshold is a constant; none of it is
model judgement, so the same history always produces the same adaptations.

| Trigger | Response |
|---|---|
| 1 session missed in a week | Absorbed — no change |
| ≥2 missed in a week | Repeat the week |
| ≥7 days without running | Rebuild from current fitness, peak back 10% |
| Long run >20% under target | Hold the long run next week |
| 3 easy runs in a row above the easy band | Flag easy-pace discipline |
| TSB < −30 | Force a recovery day |
| Goal-pace target held 3 weeks | Advance the target 5 s/km |

The first rule matters as much as the rest. Insisting on a perfect week is how a
plan gets abandoned, so a single miss produces an informational note and nothing
else.

### Background sync

Webhooks need a publicly reachable callback, which means running a tunnel.
Polling every 20 minutes costs one list request and reaches the same place
without that dependency — roughly 72 requests a day against a 1000/day budget.
Each tick syncs, then reconciles the live plan against what was actually run.

`GET /api/health` reports the last tick, its result and any error, so a silently
dead loop is visible rather than assumed working.

The gap: polling never detects *deleted* activities. Webhooks would.

---

## Coach

### The verifier

Every numeric token in the response is checked against a set derived from the
context: each scalar at any depth, the formattings the API itself emits (seconds
to `m:ss` and `h:mm:ss`, metres to kilometres, fractions to percentages), the
components of any date in the context, and any figure spelled out in the
context's own strings.

Fail once, retry with the offending tokens named. Fail twice, return a summary
assembled directly from the context, which passes by construction.

A collision is possible — 4.16 rounds to "4", so a stray "4" passes — but the
guard exists to stop fabrication, not ambiguity, and every string in the allowed
set traces back to a value that was actually computed.

### What the guard does not do

It proves a number is real. It cannot prove the sentence around it is right.

Every mislabel observed in testing traced back to an **ambiguous field name in
the context**, not to model error: `weekly_km_overall` was reported as "this
week", and so was `current_weekly_km` — which is in fact the four-week average.
Both were renamed. If the coach describes a number wrongly, look at what the
field is called before blaming the model.

There is a second blind spot. When the context shape changed underneath the
fallback summary, it degraded to *"Projected unknown … None km/week"* — and the
verifier passed it, because absent text has no numbers to object to. A guard
against fabrication is not a guard against emptiness, so emptiness has its own
test.

### Display-first context

The context carries `"2:01:08"`, not `7268`; `15.01` km, not `15008.8` m.

Instructing the model to "prefer readable units" did not work at any prompt
wording — it kept printing raw seconds and metres. Removing raw SI from the
context makes that structurally impossible instead. Same principle as the
verifier: do not ask, make it so. It also cut the payload by roughly 30%.

### No streaming

Verification needs the complete response before any of it can be trusted, so
streaming raw model output would mean showing text the guard has not cleared —
and possibly retracting it mid-sentence. The guard is the entire justification
for using a free-tier model, so it wins over the typing effect.

### Cost

A rejected answer costs a second call. The binding limit turned out not to be
requests at all: the provider allowed 1000 requests a day but only **8000 tokens
per minute**, and the context is ~1300 tokens per call, so a question plus its
retry spends ~2600. Two questions in quick succession hit the ceiling long
before the request cap.

Hence the lean context, compact JSON serialisation, and a 429 message that
reports the reset window.

---

## Within-run analysis

### Splits, not laps

`laps` is a manual-button artefact. For an athlete who never presses it, every
activity reports exactly one lap spanning the whole run and carries no
within-run information at all. `splits_metric` gives clean per-kilometre splits
instead.

A trailing partial kilometre is excluded from fade analysis — a run ending at
5.2 km has a 200 m "kilometre" whose pace is noise, and letting it define the
finish makes every run look like a collapse or a sprint.

### Aerobic decoupling

Compares output per heartbeat between the two halves of a run. Positive means
the second half cost more heartbeats for the same output.

Preferred form is **Pw:HR** where the device records real running power, falling
back to the conventional **Pa:HR**. Above 5%, aerobic durability is the limiter.

Without heart rate it returns `None` with a reason attached, never a fabricated
zero: a missing measurement and a good measurement must not look alike.

Stopped samples are excluded — standing at a crossing is not a collapse in
output.

---

## Charts

Four charts, each answering a different question, none a second way of drawing
the same thing:

| Chart | Form | Why |
|---|---|---|
| Weekly volume | Bars | Magnitude over a short ordered span |
| Every run by date | Scatter | Long-run progression *and* the gaps at once |
| Pace at distance | Line + markers, log x | Each marker is one real recorded effort |
| Fitness / fatigue | Two lines, **one** axis | CTL and ATL share units — a second y-axis would let them cross wherever the scaling put them |

Series colours were validated rather than chosen: lightness band, chroma floor,
colourblind separation, normal-vision separation and contrast, against each
mode's own surface. Dark mode is a separate set of steps for the dark surface,
not an inverted light palette.

Identity is never carried by hue alone — the two-series chart ships a legend
*and* end-of-line direct labels.
