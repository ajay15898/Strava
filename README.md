# Pace — a Strava-backed running coach for a sub-2:00 half marathon

Personal training platform that ingests Strava activity data, maintains a performance
model, and runs an AI coaching layer on top of a deterministic training engine.

**Goal:** half marathon under 2:00:00 (5:41/km sustained for 21.1 km).

**Status:** M1–M6 are built. M7 (streams) is not started.

**Race:** 2026-10-04. Seven weeks — see [The build](#the-build).

---

## Baseline

Computed from Strava history, 2026-03-14 → 2026-08-16, by the code in
`backend/app/analytics/`. Every number below is asserted in
`backend/tests/test_baseline.py`, so this table cannot drift from the
implementation without turning the suite red.

**51 runs across 50 run days · 290.9 km** after deduplication and noise
filtering. (2026-03-17 holds two separate runs, which is why the two counts
differ; the monthly `Run days` column sums to 50, not 51.)

Verified end to end against the live Strava API on 2026-08-17: a full backfill
of 155 activities reproduced every figure in this section exactly, flagged the
same three duplicates, and returned the same `tight` verdict.

### Volume

| Month | Distance | Run days | Avg/week |
|---|---|---|---|
| Mar (from 14th) | 52.0 km | 11 | 20.2 km |
| Apr | 66.8 km | 12 | 15.6 km |
| May | 32.6 km | 6 | 7.4 km |
| Jun | 42.2 km | 7 | 9.8 km |
| Jul | 50.2 km | 7 | 11.3 km |
| Aug (1–16) | 47.3 km | 7 | 20.7 km |

Five-month average: **13.05 km/week**. Last two weeks: **23.63 km/week**.
Trailing four weeks: **13.58 km/week**.

### Current fitness

| Metric | Value | Source |
|---|---|---|
| Best 5K | **25:18** | `best_effort` Fastest5k, 2026-08-15 |
| Longest run | 15.01 km @ 6:59/km | 2026-08-08 |
| Second longest | 12.50 km @ 7:38/km | 2026-07-11 |
| Riegel HM (e=1.06) | 1:56:23 | from the measured 5K |
| Cameron HM | 1:56:12 | from the measured 5K |
| Blended + durability penalty | **~2:01** | see below |
| Durability ratio | 0.71 | longest run ÷ race distance |
| Estimated FTP (run power) | 133 W | Strava estimated |

### Corrections to the original spec

Four errors in the first draft of this document, each now pinned by a test:

1. **"Best 5K 24:57" was not a 5K.** That figure is the `moving_time` of the
   2026-08-15 activity over **4992.59 m** — seven metres short, on the more
   generous clock. Strava's own `Fastest5k` for that same activity is
   **1518 s (25:18)**. Predictions now seed from `best_effort` rows and never
   from activity `moving_time`.

2. **The dedup tie-break contradicted the volume table.** The rule says keep the
   record with more populated fields; the original table was computed keeping
   the *longer* record. June differed by exactly 200.7 m — the
   `6880.00 → 6679.29` pair on 2026-06-04. The spec's rule now wins, and the
   table above is regenerated from it.

3. **March had 11 run days, not 12.** 2026-03-18's only run is the 19 m noise
   record. The noise floor now applies to day counting as well as distance;
   `analytics/base.py` defines "an analysable run" exactly once so the two can
   never diverge again.

4. **The heart-rate gap predates August.** 2026-07-11 also returns
   `has_heartrate: false`. The flag is derived from data, never hardcoded to a
   month.

### The prediction, honestly

The original "~1:54" rested on Strava's *modeled* 5K prediction (24:44) plus the
friendlier Riegel exponent. On measured data:

| 5K source | e=1.06 | e=1.08 | e=1.10 |
|---|---|---|---|
| Strava prediction (modeled) 24:44 | 1:53:47 | 1:57:06 | 2:00:31 |
| Aug-15 moving_time (4992.6 m) 24:57 | 1:54:57 | 1:58:19 | 2:01:47 |
| **Aug-15 measured Fastest5k 25:18** | **1:56:23** | 1:59:47 | 2:03:17 |

The break-even exponent on measured data is **1.081**. Riegel and Cameron agree
within about 1% over this range, so the formula choice is not what decides the
verdict — durability is. With a 15.01 km longest run against 21.10 km, the
final 6 km are unrehearsed, which is exactly where speed extrapolation
over-predicts. The engine applies a **4.16%** durability penalty, putting the
projection just past 2:00 and the verdict at `tight` with
`limiting_factor: long_run_durability`.

The speed is close. The endurance is the gap. That is still the thesis — the
original document was right about the shape and optimistic about the margin.

### The three real constraints

1. **Volume is roughly a third of what a sub-2:00 build needs.** Sustained level
   is ~13 km/week against a 45 km/week peak target.
2. **Consistency, not speed, is the limiter.** Gaps of 9–11 days recur: five of
   them in the window, the longest ending 2026-08-06.
3. **No heart rate.** Effort data is power-only, which makes aerobic-drift and
   easy-pace-discipline checks impossible. Fix at the watch before the first
   build week.

Weekly run-day counts for the last eight weeks are `[2, 2, 2, 2, 1, 0, 4, 3]`.
The plan assumes 4/week rising to 5; only one week in eight has hit 4. The
planner takes `max_sessions_per_week` as an athlete constraint rather than
assuming.


---

## The build

The race is 2026-10-04, which is **six weeks out, not fourteen**. That is below
the planner's original eight-week floor. The floor was lowered to six
deliberately, because modelling the actual block showed the goal is still
reachable — and the reason is worth stating plainly:

**What moves this athlete's projection is long-run distance, not weekly mileage.**

| longest run | ratio | penalty | projected |
|---|---|---|---|
| 15.01 km (today) | 0.711 | 4.16% | 2:01:07 |
| 17.00 km | 0.806 | 1.33% | 1:57:50 |
| **17.93 km** | 0.850 | **0.00%** | **1:56:17** |
| 20.00 km | 0.948 | 0.00% | 1:56:17 |

The durability penalty reaches zero at 17.93 km. Everything past that is free.
So the block is built around getting the long run from 15.01 km to 20 km, and
weekly volume is *derived* from it rather than the other way round —
`LONG_RUN_WEEK_SHARE = 0.55` sizes the week to carry its long run. Sizing it the
other way (a 70% share cap applied after the fact) produced 2–3 km easy runs,
which is not a training stimulus.

`HM_PEAK_WEEKLY_KM = 45` is therefore *not* consulted by the engine. It is a
generic guideline that nothing in the prediction path reads.

### The plan

Seven weeks, anchored to the Monday just gone rather than the next one — with a
compressed block a week of runway is worth more than a tidy start date, and any
session already in the past is simply reconciled against what was actually run.

Four runs a week: one threshold, one long, two easy. Two quality days were
considered and rejected — every fitness regression in this athlete's history
follows a gap rather than a bad session, and a second hard day is the reliable
way to cause one.

```
        Tue easy    Wed threshold   Sat LONG    Sun social      week
W1  17 Aug   4.2         7.0 (3x8)      15.0         8.0       34.2
W2  24 Aug   4.8         7.0 (3x8)      17.3         8.0       37.1
W3  31 Aug   5.6         7.0 (3x8)      19.9         8.0       40.4   <- clears 17.93
W4  07 Sep   5.6         7.0 (3x8)      20.0         8.0       40.6
W5  14 Sep   5.6         7.0 (3x8)      20.0         8.0       40.6
W6  21 Sep   4.0         5.2 (2x6)      14.0         6.0       29.2   taper
W7  28 Sep   5.0    Thu shakeout 4.0    RACE 21.1 Sunday        9.0
```

Paces derived from the measured 25:18 5 K, never a fixed table: easy
6:34–7:05, long 6:19–6:49, threshold 5:15–5:27, goal 5:36–5:46 /km. The Sunday
social run carries its own fixed 8 km at 6:50.

### Why the days sit where they do

Two standing commitments were given: a threshold run and a Sunday social 8 km.
The originally proposed order was Friday threshold → Saturday long → Sunday
social, which the engine now flags automatically:

> *Friday's threshold session sits directly before Saturday's long run. The long
> run is the session that moves the goal, and it would be run on tired legs.*

Moving the quality day to Wednesday fixes it and turns the Sunday social run
from a third consecutive day into a recovery run on the previous day's legs —
which is itself a durability stimulus, and durability is the limiter. The
pattern lives in `athlete.preferences` as JSON, so it is athlete configuration
rather than an engine assumption, and `_warn_about_ordering` catches the
adjacency for any pattern.

Threshold pace was also given as 5:10/km. Derived threshold is 5:15–5:27; 5:10
sits in the interval band. Against a 25:18 5 K and a best 6.6 km of 5:27/km, a
7 km continuous at 5:10 would be a new benchmark rather than a repeatable
weekly session.

### What the plan costs

The engine emits these with the plan rather than burying them:

1. **Compressed build.** Seven weeks means no base phase and a one-week taper.
2. **Volume rises above the 8%/week cap in W1–W3, peaking at +31%.** Four runs a
   week including a 20 km long run comes to about 41 km, against a 23.6 km
   two-week average. This is the plan's main injury risk. If anything aches,
   cut the easy runs before the long run.


---

## Architecture

```
┌─────────────┐   OAuth2 + webhooks   ┌──────────────────┐
│   Strava    │ ────────────────────► │  Ingest service  │
└─────────────┘                       └────────┬─────────┘
                                               │ normalized activities
                                               ▼
                                      ┌──────────────────┐
                                      │    Postgres      │
                                      └────────┬─────────┘
                                               │
                     ┌─────────────────────────┼─────────────────────────┐
                     ▼                         ▼                         ▼
           ┌──────────────────┐      ┌──────────────────┐     ┌──────────────────┐
           │ Performance      │      │ Training engine  │     │  Coach service   │
           │ model            │─────►│ (deterministic)  │────►│  (LLM + guard)   │
           │ CTL/ATL, curves  │      │ plan generation, │     │  explains only   │
           │ consistency      │      │ adaptation rules │     │  never computes  │
           └──────────────────┘      └──────────────────┘     └──────────────────┘
                    built                  not started              not started
```

**Stack:** FastAPI + SQLAlchemy 2 + Postgres + Alembic · React 19 / TypeScript /
Vite / Tailwind v4 / Recharts / Framer Motion · any OpenAI-compatible LLM for the
coach · Docker Compose.

### The design rule

The LLM sits at the end of the pipeline, not the middle. It receives a
`CoachContext` that has already been computed and validated. It may paraphrase,
prioritise, and explain. It may not produce a number that isn't in the context.
A verifier extracts every numeric token from the output and asserts membership
in the context before the response reaches the client.

Every threshold that shapes a training decision lives in `app/constants.py`
with the reasoning attached. Nothing in the analytics path is model judgement.

---

## What's built

```
backend/
├── alembic/versions/0001_initial_schema.py   9 tables
└── app/
    ├── constants.py        every tunable threshold, with its rationale
    ├── models/             Athlete, OAuthToken, Activity, ActivityStream,
    │                       BestEffort, DailyLoad, Plan, PlanSession, CoachMessage
    ├── strava/
    │   ├── client.py       rate limiter driven by response headers, 429 backoff
    │   ├── oauth.py        authorize / callback / refresh with token rotation
    │   └── sync.py         backfill, incremental, normalize, dedup
    ├── analytics/
    │   ├── base.py         the single definition of "an analysable run"
    │   ├── consistency.py  volume rollups, gaps, weekly/monthly summaries
    │   ├── curves.py       pace-at-distance from best_effort rows
    │   ├── load.py         rTSS → CTL / ATL / TSB
    │   └── predict.py      Riegel + Cameron, blended, durability-penalised
    └── api/routes/         auth, sync, activities, analytics
```

### Endpoints

```
GET    /api/health
GET    /api/auth/strava/authorize        → redirect
GET    /api/auth/strava/callback
POST   /api/auth/refresh

POST   /api/sync/backfill                → background historical import
POST   /api/sync/incremental
POST   /api/sync/dedup                   → idempotent re-scan

GET    /api/activities?from=&to=&type=&include_duplicates=
GET    /api/activities/{id}
GET    /api/activities/{id}/streams

GET    /api/analytics/summary?from=&to=
GET    /api/analytics/load
GET    /api/analytics/curve
GET    /api/analytics/prediction?distance=21097.5
GET    /api/analytics/feasibility
```

---

## Design decisions worth knowing

**Deduplication.** Same sport, start within 300 s, distance within 5% → keep the
record with more populated fields, flag the other. Never hard-deleted. The
window was widened from 120 s because the real 2026-03-14 pair is 112 s apart —
eight seconds of margin. Verified against 2026-03-17, which holds two *genuine*
runs 23 minutes apart; the distance guard separates them.

**Noise floor.** Activities under 500 m are excluded from every analytic,
including run-day counting, and kept in the table.

**Reference effort selection.** The predictor picks the effort implying the
fastest target time, among efforts at least 20% of the target distance. This
sidesteps detecting whether an effort was maximal — which is not reliably
possible without heart rate, since a 15 K effort inside a 15.01 km run spans the
whole activity and trivially "looks" maximal. Ranking by implied performance
discards easy efforts automatically.

**Training load without heart rate.** Strava's Relative Effort is HR-derived and
unavailable here, so load falls back to running TSS from pace against threshold
pace (Z4 lower bound, 3.207 m/s). Relative Effort is still preferred when
present.

**Best efforts are free.** Strava returns them on the activity detail payload, so
the pace-at-distance curve needs no stream data. That moves the curve out of the
streams milestone entirely.

**Rate limits are read, not assumed.** This app's actual read budget is
**100 per 15 min / 1,000 per day** — an order of magnitude below the 600/30,000
figures that circulate in older documentation. A hardcoded limiter would have
sailed past the real cap. `strava/client.py` parses `X-ReadRateLimit-*` off
every response and pauses before crossing it. A full backfill costs about 50
requests, so it fits comfortably, but a streams backfill (M7) will not — that
one needs to be paced across days.

**Reference efforts expire.** The best 10 K on record is 61:07 from 2026-04-25,
which is outside the 90-day window and correctly ignored; it would project
2:14:50 and badly misdescribe current fitness. Recency filtering is doing real
work here, not just hygiene.

---

## Local setup

```bash
cp .env.example .env        # fill in Strava credentials
docker compose up -d db

cd backend
python -m venv .venv && .venv/Scripts/activate    # Windows
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Strava app settings (https://www.strava.com/settings/api): Authorization
Callback Domain must be `localhost`, and the redirect URI must match
`STRAVA_REDIRECT_URI` exactly, including port.

Then `GET /api/auth/strava/authorize` to connect, and
`POST /api/sync/backfill` to import.

### Tests

```bash
cd backend && python -m pytest
```

44 tests, no database required. `test_baseline.py` asserts the published
baseline reproduces from code; `test_queries.py` exercises the real ingest path
and SQLAlchemy queries on in-memory SQLite.

---

## Coach

Provider-agnostic, running on a free tier. The model never computes anything —
it paraphrases a `CoachContext` that was fully computed first, and every number
it prints is checked before the athlete sees it.

### The verifier

`coach/verify.py` extracts every numeric token from the response and asserts
membership in a set derived from the context: each scalar at any depth, plus the
formattings the API itself emits (seconds to `m:ss` and `h:mm:ss`, metres to
kilometres, fractions to percentages) and any figure spelled out in the
context's own strings. Fail once, retry with the offending tokens named. Fail
twice, return `templated_summary`, which is assembled from the context directly
and therefore passes by construction.

A prompt instruction is not a control. This is:

```
"You are 68 seconds off the goal."   -> rejected
```

7268 − 7200 = 68 is arithmetically correct and still refused, because the coach
does not compute. That test is in `tests/test_coach.py`.

### Why streaming was dropped

The spec said stream to the client. It does not, and the reason is structural:
verification needs the complete response before any of it can be trusted, so
streaming raw output would mean showing text the guard has not cleared — and
possibly retracting it mid-sentence. The guard is the whole justification for
using a free-tier model, so it wins over the typing effect.

### Cost

A rejected answer costs a second call, so one question can be two requests. At
Groq's 30 RPM / 1000 RPD that is nowhere near binding for one athlete, but it is
why the fallback exists rather than retrying indefinitely.

`GET /api/coach/context` returns the exact object the model is given, and
`POST /api/coach/reverify/{id}` re-runs the guard over a stored answer against
its own snapshot — a coach whose inputs cannot be inspected cannot be audited.

---

## Adaptation

Six rules, run on every ingest and readable at `GET /api/plan/adaptations`.
Every threshold is a constant in `app/constants.py`; none of it is model
judgement, so the same history always produces the same adaptations.

| Trigger | Response |
|---|---|
| 1 session missed in a week | Absorbed — no change, and deliberately no nagging |
| ≥2 missed in a week | Repeat the week rather than stepping the long run up on training that did not happen |
| ≥7 days without running | Rebuild from current fitness, peak target pulled back 10% |
| Long run >20% under target | Hold the long run at that distance next week |
| 3 easy runs in a row above the easy band | Flag easy-pace discipline |
| TSB < −30 | Force a recovery day before the next quality session |
| Goal-pace target held 3 weeks | Advance the target 5 s/km *(dormant — this week pattern prescribes threshold, not goal-pace, sessions)* |

The first rule matters as much as the rest: insisting on a perfect week is how
a plan gets abandoned, so a single miss produces an `info` note and nothing
else.

`GET /api/plan/digest` gives the week in review — prescribed against actual,
session count, and any adaptations that fired.

### Background sync

Strava webhooks need a publicly reachable callback, which means running a
tunnel. Polling every 20 minutes costs one list request and reaches the same
place without that dependency — roughly 72 requests a day against a 1000/day
read budget. Each tick syncs, then reconciles the live plan against what was
actually run. `GET /api/health` reports the last tick, its result and any error,
so a silently dead loop is visible rather than assumed working.

---

## Frontend

```
frontend/src/
├── api/            typed client mirroring the backend schemas
├── lib/            theme (light/dark tokens), formatters, fetch hook
├── components/     Panel, StatTile, Skeleton, States, tooltip/legend
└── features/
    ├── dashboard/  PredictionHero, VolumeChart, LoadChart, PaceCurve, RunScatter
    └── activities/ ActivityTable
```

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

Vite proxies `/api` to `http://127.0.0.1:8000`, so the client is origin-relative
and CORS never enters the picture. The dev server binds to `localhost` (IPv6);
`127.0.0.1:5173` will not answer.

### Chart decisions

The four charts each answer a different question, and none of them is a second
way of drawing the same thing:

| Chart | Form | Why |
|---|---|---|
| Weekly volume | Bars, 8 weeks | Magnitude over a short ordered span |
| Every run by date | Scatter | Shows long-run progression *and* the gaps at once |
| Pace at distance | Line + markers, log x | Each marker is one real recorded effort |
| Fitness / fatigue | Two lines, one axis | CTL and ATL share units — a second y-axis would let them cross wherever the scaling put them |

Series colors are `#2a78d6` / `#eb6834` in light and `#3987e5` / `#d95926` in
dark — both pairs validated against their own surface for lightness band,
chroma, colorblind separation, normal-vision separation and contrast. Identity
is never carried by hue alone: the two-series chart ships a legend *and*
end-of-line direct labels. Dark mode is a separate set of steps chosen for the
dark surface, not an inverted light palette.

## Coach LLM

Provider-agnostic: any OpenAI-compatible chat-completions endpoint, configured
by `COACH_BASE_URL` / `COACH_MODEL` / `COACH_API_KEY`. Free tiers are viable
here because the coach never computes numbers. See
`backend/app/coach/README.md` for the trade-offs.

---

## Build order

- [x] **M1 — Ingest.** OAuth, token refresh, backfill, dedup, Postgres schema.
- [x] **M2 — Analytics.** Volume rollups, consistency, pace-at-distance curve,
      load series, race prediction, feasibility.
- [x] **M3 — Dashboard.** Prediction hero, weekly volume, run scatter, pace
      curve, fitness/fatigue, gap list, activity table. Read-only.
- [x] **M4 — Planner.** Deterministic engine, pace derivation, phase templates,
      plan versioning, activity reconciliation, session detail and completion.
- [x] **M5 — Coach.** CoachContext, prompt contract, numeric verifier, chat UI.
      Verifier shipped with the model call, as specified.
- [x] **M6 — Adaptation.** Background sync, six deterministic adaptation rules,
      weekly digest. Plan versioning shipped with M4.
- [ ] **M7 — Streams.** Lazy stream fetch, per-run charts, aerobic decoupling.

Not yet built, deferred deliberately from M1: **webhooks**
(`/api/webhooks/strava`, `hub.challenge` echo). The build order places them
after ingest, and incremental sync covers the need until then.

---

## Open questions

- **Race choice.** 2026-11-29 is derived from a 14-week window, not a real
  event. Magdeburg and Berlin both have autumn options. Plan quality depends on
  a fixed date.
- **Durability calibration.** `DURABILITY_K = 0.30` is reasoned, not fitted —
  chosen so an athlete who has never run past half the race distance carries
  roughly a 10% penalty. One completed half marathon would let it be calibrated
  against reality rather than argument.
- **Strength work.** March–April show consistent weight training that stops in
  May. Whether to model it as load or ignore it affects TSB.
- **Heart rate.** If recording resumes, add aerobic decoupling and easy-pace
  discipline checks. The flags are already derived from data, so this needs no
  code change to start reflecting reality.
