# Pace

A self-hosted running coach built on Strava data. It ingests your activity
history, maintains a performance model, generates a deterministic training plan,
adapts that plan when life gets in the way, and puts an LLM on top that can
explain the numbers but cannot invent them.

```
Strava API ──► ingest ──► Postgres ──► analytics ──► planner ──► coach (LLM)
                                           │             │          │
                                           └─────────────┴──────────┴──► React dashboard
```

---

## What it does

**Ingest** — OAuth with rotating refresh tokens, a rate limiter that reads its
budget from Strava's response headers instead of hardcoding it, incremental sync
every 20 minutes, and deduplication for when two devices record the same run.

**Analytics** — weekly and monthly volume, consistency and gap analysis,
pace-at-distance curves built from Strava's own best-effort records, training
load (CTL / ATL / TSB), and race prediction blending Riegel and Cameron with a
durability penalty for athletes whose long-run volume is thin.

**Planner** — deterministic plan generation: same inputs, same plan, every time.
Training paces derived from a measured effort rather than a fixed table, a
configurable weekly pattern with standing commitments the engine plans around,
phase templates, and plan versioning so a superseded plan stays queryable.

**Adaptation** — six rules comparing what was prescribed against what was
actually run: missed sessions, layoffs, short long runs, easy runs run too hard,
chronic fatigue, goal-pace progression. Every threshold is a named constant.

**Coach** — an LLM that reads a pre-computed context and explains it. Every
numeric token in its answer is checked before you see it.

**Within-run analysis** — lazy stream fetch, per-kilometre splits, pace charts,
split fade, and aerobic decoupling (Pw:HR, falling back to Pa:HR).

---

## The design rule

The LLM sits at the end of the pipeline, not the middle. It receives a context
object that has already been computed and validated. It may paraphrase,
prioritise and explain. It may not produce a number that isn't in that context.

`coach/verify.py` extracts every numeric token from the response and asserts
membership in a set derived from the context. Fail once, retry with the
offending tokens named. Fail twice, fall back to a summary assembled directly
from the context, which passes by construction.

```
"You are 68 seconds off the goal."   →  rejected
```

The arithmetic is correct and it is still refused, because the coach does not
compute. A prompt instruction is not a control.

Every threshold that shapes a training decision lives in
[`app/constants.py`](backend/app/constants.py) with its reasoning attached.
Nothing in the analytics or planning path is model judgement.

---

## Quick start

Requires Docker and a [Strava API application](https://www.strava.com/settings/api)
with its Authorization Callback Domain set to `localhost`.

```bash
git clone https://github.com/ajay15898/Strava.git && cd Strava
cp .env.example .env          # add your Strava client id and secret

docker compose up -d
```

That is the whole thing. The image builds the frontend and serves it from the
same container as the API, migrations run on start, and both services carry
`restart: unless-stopped` so the stack comes back after a reboot and keeps
syncing whether or not anyone is looking at it.

Open <http://localhost:8000>, connect Strava, then `POST /api/sync/backfill`.

### Developing

Running the pieces separately gives hot reload on both sides:

```bash
docker compose up -d db       # Postgres only

cd backend
python -m venv .venv && .venv/Scripts/activate    # or: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000

cd ../frontend && npm install && npm run dev       # http://localhost:5173
```

The Vite dev server proxies `/api` to the backend, so the client stays
origin-relative in both modes.

> Vite binds to `localhost` (IPv6). `127.0.0.1:5173` will not answer.

### The coach (optional)

Any OpenAI-compatible chat-completions endpoint. Free tiers are adequate,
because the model never computes anything.

```env
COACH_BASE_URL=https://api.groq.com/openai/v1
COACH_MODEL=openai/gpt-oss-120b
COACH_API_KEY=
```

Model ids churn — query `GET /v1/models` against your provider before trusting
one. Provider trade-offs are in
[backend/app/coach/README.md](backend/app/coach/README.md).

### Tests

```bash
cd backend && python -m pytest
```

133 tests. Most need no database — the analytics and planner run on in-memory
model instances, and the query tests use SQLite.

---

## Layout

```
backend/
├── alembic/            4 migrations
└── app/
    ├── constants.py    every tunable threshold, with its rationale
    ├── models/         activities, streams, splits, plans, coach messages
    ├── strava/         OAuth, rate-limited client, sync, dedup
    ├── analytics/      volume, curves, load, prediction, within-run streams
    ├── planner/        pace derivation, phases, engine, adaptation
    ├── coach/          context, prompt, verifier, service
    └── api/routes/     31 endpoints
frontend/src/
├── api/                typed client
├── lib/                theme, formatters, fetch hook
├── components/         panels, tiles, skeletons, states
└── features/           dashboard, plan, coach, activities
```

**Stack** — FastAPI · SQLAlchemy 2 · Postgres · Alembic · React 19 · TypeScript ·
Vite · Tailwind v4 · Recharts · Framer Motion.

---

## Documentation

**[docs/DESIGN.md](docs/DESIGN.md)** — why the engine works the way it does.
Deduplication rules, the durability penalty, why weekly volume is derived from
the long run rather than the reverse, what a numeric guard cannot protect
against, and the chart decisions. Most of it was forced by real data rather than
chosen in the abstract.

---

## Status

All seven milestones are built: ingest, analytics, dashboard, planner, coach,
adaptation, streams.

Not built:

- **Strava webhooks.** Sync polls every 20 minutes instead, which works but
  never detects deleted activities.
- **Code-splitting.** The frontend bundle is ~835 KB (~246 KB gzipped), mostly
  Recharts and Framer Motion.
- **Remote deployment.** The stack is containerised and survives reboots, but
  it is only configured for localhost. Running it on a server would need a real
  hostname in `STRAVA_REDIRECT_URI` and a reverse proxy for TLS.
