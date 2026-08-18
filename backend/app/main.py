import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
