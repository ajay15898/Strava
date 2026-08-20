import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import activities, analytics, athlete, auth, coach, plan, sync
from app.config import get_settings
from app import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    task = scheduler.start()
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="Pace",
    version="0.4.0",
    description="Strava-backed running coach",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sync.router)
app.include_router(athlete.router)
app.include_router(activities.router)
app.include_router(analytics.router)
app.include_router(plan.router)
app.include_router(coach.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "strava_configured": bool(settings.strava_client_id),
        "coach_configured": settings.coach_configured,
        "sync": scheduler.last_run,
    }


# The built frontend, when there is one.
#
# This must stay at the very bottom of the file. Starlette resolves routes in
# registration order, so a mount at "/" swallows everything registered after
# it. Declared above the health route, it returned 404 for /api/health while
# the routers included earlier kept working — a confusing half-failure.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    logging.getLogger(__name__).info("serving built frontend from %s", STATIC_DIR)
